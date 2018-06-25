# Copyright 2015 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from abc import ABC, abstractmethod
import attr
import collections
import enum
import glob
import logging
import math
import os
import sys

log = logging.getLogger('subiquity.models.filesystem')


@attr.s(cmp=False)
class FS:
    label = attr.ib()
    is_mounted = attr.ib()


@attr.s(cmp=False)
class RaidLevel:
    name = attr.ib()
    value = attr.ib()
    min_devices = attr.ib()
    supports_spares = attr.ib(default=True)


raidlevels = [
    RaidLevel(_("0 (striped)"),  0,  2, False),
    RaidLevel(_("1 (mirrored)"), 1,  2),
    RaidLevel(_("5"),            5,  3),
    RaidLevel(_("6"),            6,  4),
    RaidLevel(_("10"),           10, 4),
    ]
raidlevels_by_value = {l.value: l for l in raidlevels}


HUMAN_UNITS = ['B', 'K', 'M', 'G', 'T', 'P']


def humanize_size(size):
    if size == 0:
        return "0B"
    p = int(math.floor(math.log(size, 2) / 10))
    # We want to truncate the non-integral part, not round to nearest.
    s = "{:.17f}".format(size / 2 ** (10 * p))
    i = s.index('.')
    s = s[:i + 4]
    return s + HUMAN_UNITS[int(p)]


def dehumanize_size(size):
    # convert human 'size' to integer
    size_in = size

    if not size:
        raise ValueError("input cannot be empty")

    if not size[-1].isdigit():
        suffix = size[-1].upper()
        size = size[:-1]
    else:
        suffix = None

    parts = size.split('.')
    if len(parts) > 2:
        raise ValueError(_("{!r} is not valid input").format(size_in))
    elif len(parts) == 2:
        div = 10 ** len(parts[1])
        size = parts[0] + parts[1]
    else:
        div = 1

    try:
        num = int(size)
    except ValueError:
        raise ValueError(_("{!r} is not valid input").format(size_in))

    if suffix is not None:
        if suffix not in HUMAN_UNITS:
            raise ValueError(
                "unrecognized suffix {!r} in {!r}".format(size_in[-1],
                                                          size_in))
        mult = 2 ** (10 * HUMAN_UNITS.index(suffix))
    else:
        mult = 1

    if num < 0:
        raise ValueError("{!r}: cannot be negative".format(size_in))

    return num * mult // div


def get_raid_size(level, devices):
    if len(devices) == 0:
        return 0
    min_size = min(dev.size for dev in devices)
    if min_size <= 0:
        return 0
    if level == 0:
        return min_size * len(devices)
    elif level == 1:
        return min_size
    elif level == 5:
        return min_size * (len(devices) - 1)
    elif level == 6:
        return min_size * (len(devices) - 2)
    elif level == 10:
        return min_size * (len(devices) // 2)
    else:
        raise ValueError("unknown raid level %s" % level)


def id_factory(name):
    i = 0

    def factory():
        nonlocal i
        r = "%s-%s" % (name, i)
        i += 1
        return r
    return attr.Factory(factory)


def asdict(inst):
    r = collections.OrderedDict()
    for field in attr.fields(type(inst)):
        if field.name.startswith('_'):
            continue
        v = getattr(inst, field.name)
        if v is not None:
            if isinstance(v, (list, set)):
                r[field.name] = [elem.id for elem in v]
            else:
                if hasattr(v, 'id'):
                    v = v.id
                if v is not None:
                    r[field.name] = v
    return r


# This code is not going to make much sense unless you have read
# http://curtin.readthedocs.io/en/latest/topics/storage.html. The
# Disk, Partition etc classes correspond to entries in curtin's
# storage config list. They are mostly 'dumb data', all the logic is
# in the FilesystemModel or FilesystemController classes.


class DeviceAction(enum.Enum):
    INFO = enum.auto()
    EDIT = enum.auto()
    PARTITION = enum.auto()
    FORMAT = enum.auto()
    DELETE = enum.auto()
    MAKE_BOOT = enum.auto()


@attr.s(cmp=False)
class _Formattable:
    # Base class for anything that can be formatted and mounted,
    # e.g. a disk or a RAID or a partition.

    # Filesystem
    _fs = attr.ib(default=None, repr=False)
    # Raid for now, but one day LV, ZPool, BCache...
    _constructed_device = attr.ib(default=None, repr=False)

    def _is_entirely_used(self):
        return self._fs is not None or self._constructed_device is not None

    def fs(self):
        return self._fs

    def constructed_device(self):
        return self._constructed_device

    def supports_action(self, action):
        return getattr(self, "_supports_" + action.name)


# Nothing is put in the first and last megabytes of the disk to allow
# space for the GPT data.
GPT_OVERHEAD = 2 * (1 << 20)


@attr.s(cmp=False)
class _Device(_Formattable, ABC):
    # Anything that can have partitions, e.g. a disk or a RAID.

    @property
    @abstractmethod
    def size(self):
        pass

    # [Partition]
    _partitions = attr.ib(default=attr.Factory(list), repr=False)

    def partitions(self):
        return self._partitions

    @property
    def used(self):
        if self._is_entirely_used():
            return self.size
        r = 0
        for p in self._partitions:
            r += p.size
        return r

    @property
    def empty(self):
        return self.used == 0

    @property
    def free_for_partitions(self):
        return self.size - self.used - GPT_OVERHEAD

    def available(self):
        # A _Device is available if:
        # 1) it is not part of a device like a RAID or LVM or zpool or ...
        # 2) if it is formatted, it is available if it is formatted with fs
        #    that needs to be mounted and is not mounted
        # 3) if it is not formatted, it is available if it has free
        #    space OR at least one partition is not formatted or is formatted
        #    with a fs that needs to be mounted and is not mounted
        if self._constructed_device is not None:
            return False
        if self._fs is not None:
            return self._fs._available()
        if self.free_for_partitions > 0:
            return True
        for p in self._partitions:
            if p.available():
                return True
        return False

    def has_unavailable_partition(self):
        for p in self._partitions:
            if not p.available():
                return True
        return False


@attr.s(cmp=False)
class Disk(_Device):

    id = attr.ib(default=id_factory("disk"))
    type = attr.ib(default="disk")
    ptable = attr.ib(default=None)
    serial = attr.ib(default=None)
    path = attr.ib(default=None)
    model = attr.ib(default=None)
    wipe = attr.ib(default='superblock')
    preserve = attr.ib(default=False)
    name = attr.ib(default="")
    grub_device = attr.ib(default=False)

    _info = attr.ib(default=None)

    @classmethod
    def from_info(self, info):
        d = Disk(info=info)
        d.serial = info.serial
        d.path = info.name
        d.model = info.model
        return d

    def info_for_display(self):
        bus = self._info.raw.get('ID_BUS', None)
        major = self._info.raw.get('MAJOR', None)
        if bus is None and major == '253':
            bus = 'virtio'

        devpath = self._info.raw.get('DEVPATH', self.path)
        # XXX probert should be doing this!!
        rotational = '1'
        try:
            dev = os.path.basename(devpath)
            rfile = '/sys/class/block/{}/queue/rotational'.format(dev)
            rotational = open(rfile, 'r').read().strip()
        except (PermissionError, FileNotFoundError, IOError):
            log.exception('WARNING: Failed to read file {}'.format(rfile))
            pass

        dinfo = {
            'bus': bus,
            'devname': self.path,
            'devpath': devpath,
            'model': self.model,
            'serial': self.serial,
            'size': self.size,
            'humansize': humanize_size(self.size),
            'vendor': self._info.vendor,
            'rotational': 'true' if rotational == '1' else 'false',
        }
        if dinfo['serial'] is None:
            dinfo['serial'] = 'unknown'
        if dinfo['model'] is None:
            dinfo['model'] = 'unknown'
        if dinfo['vendor'] is None:
            dinfo['vendor'] = 'unknown'
        return dinfo

    def reset(self):
        self.preserve = False
        self.name = ''
        self.grub_device = False
        self._partitions = []
        self._fs = None
        self._constructed_device = None

    @property
    def size(self):
        return align_down(self._info.size)

    def desc(self):
        return _("local disk")

    @property
    def label(self):
        if self.serial is not None:
            return self.serial
        return self.path

    _supports_INFO = True
    _supports_EDIT = False
    _supports_PARTITION = property(lambda self: self.free_for_partitions > 0)
    _supports_FORMAT = property(
        lambda self: len(self._partitions) == 0 and
        self._constructed_device is None)
    _supports_DELETE = False
    _supports_MAKE_BOOT = property(
        lambda self:
        not self.grub_device and self._fs is None
        and self._constructed_device is None)


@attr.s(cmp=False)
class Partition(_Formattable):

    id = attr.ib(default=id_factory("part"))
    type = attr.ib(default="partition")
    device = attr.ib(default=None)  # Disk
    size = attr.ib(default=None)
    wipe = attr.ib(default=None)
    flag = attr.ib(default=None)
    preserve = attr.ib(default=False)

    def desc(self):
        return _("partition of {}").format(self.device.desc())

    @property
    def label(self):
        return _("partition {} of {}").format(self._number, self.device.label)

    def available(self):
        if self.flag == 'bios_grub':
            return False
        if self._constructed_device is not None:
            return False
        if self._fs is None:
            return True
        return self._fs._available()

    @property
    def _number(self):
        return self.device._partitions.index(self) + 1

    @property
    def path(self):
        return "%s%s" % (self.device.path, self._number)

    _supports_INFO = False
    _supports_EDIT = True
    _supports_PARTITION = False
    _supports_FORMAT = property(
        lambda self: self.flag not in ('boot', 'bios_grub') and
        self._constructed_device is None)
    _supports_DELETE = property(
        lambda self: self.flag not in ('boot', 'bios_grub'))
    _supports_MAKE_BOOT = False


@attr.s(cmp=False)
class Raid(_Device):
    id = attr.ib(default=id_factory("raid"))
    type = attr.ib(default="raid")
    name = attr.ib(default=None)
    raidlevel = attr.ib(default=None)  # 0, 1, 5, 6, 10
    devices = attr.ib(default=attr.Factory(set))  # set([_Formattable])
    spare_devices = attr.ib(default=attr.Factory(set))  # set([_Formattable])
    ptable = attr.ib(default=None)

    @property
    def size(self):
        return get_raid_size(self.raidlevel, self.devices)

    @property
    def label(self):
        return self.name

    def desc(self):
        return _("software RAID {}").format(self.raidlevel)

    _supports_INFO = False
    _supports_EDIT = True
    _supports_PARTITION = Disk._supports_PARTITION
    _supports_FORMAT = property(
        lambda self: len(self._partitions) == 0 and
        self._constructed_device is None)
    _supports_DELETE = True
    _supports_MAKE_BOOT = False

    @property
    def path(self):
        return "/dev/{}".format(self.name)


@attr.s(cmp=False)
class Filesystem:

    id = attr.ib(default=id_factory("fs"))
    type = attr.ib(default="format")
    fstype = attr.ib(default=None)
    volume = attr.ib(default=None)  # _Formattable
    label = attr.ib(default=None)
    uuid = attr.ib(default=None)
    preserve = attr.ib(default=False)

    _mount = attr.ib(default=None, repr=False)  # Mount

    def mount(self):
        return self._mount

    def _available(self):
        # False if mounted or if fs does not require a mount, True otherwise.
        if self._mount is None:
            fs_obj = FilesystemModel.fs_by_name[self.fstype]
            return fs_obj.is_mounted
        else:
            return False


@attr.s(cmp=False)
class Mount:
    id = attr.ib(default=id_factory("mount"))
    type = attr.ib(default="mount")
    device = attr.ib(default=None)  # Filesystem
    path = attr.ib(default=None)

    def can_delete(self):
        # Can't delete mount of /boot/efi or swap, anything else is fine.
        if not self.path:
            # swap mount
            return False
        if not isinstance(self.device.volume, Partition):
            # Can't be /boot/efi if volume is not a partition
            return True
        if self.device.volume.flag == "boot":
            # /boot/efi
            return False
        return True


def align_up(size, block_size=1 << 20):
    return (size + block_size - 1) & ~(block_size - 1)


def align_down(size, block_size=1 << 20):
    return size & ~(block_size - 1)


class FilesystemModel(object):

    lower_size_limit = 128 * (1 << 20)

    supported_filesystems = [
        ('ext4', True, FS('ext4', True)),
        ('xfs', True, FS('xfs', True)),
        ('btrfs', True, FS('btrfs', True)),
        ('---', False),
        ('swap', True, FS('swap', False)),
        ('---', False),
        ('leave unformatted', True, FS(None, False)),
    ]

    fs_by_name = {}
    longest_fs_name = 0
    for t in supported_filesystems:
        if len(t) > 2:
            fs = t[2]
            if fs.label is not None:
                if len(fs.label) > longest_fs_name:
                    longest_fs_name = len(fs.label)
            fs_by_name[fs.label] = fs
    fs_by_name['fat32'] = FS('fat32', True)

    def __init__(self, prober):
        self.prober = prober
        self._available_disks = {}  # keyed by path, eg /dev/sda
        self.reset()

    def reset(self):
        # only gets populated when something uses the disk
        self._disks = collections.OrderedDict()
        self._partitions = []
        self._raids = []
        self._filesystems = []
        self._mounts = []
        for k, d in self._available_disks.items():
            self._available_disks[k].reset()

    def render(self):
        r = []
        for d in self._disks.values():
            r.append(asdict(d))
        for p in self._partitions:
            r.append(asdict(p))
        for f in self._filesystems:
            r.append(asdict(f))
        for m in sorted(self._mounts, key=lambda m: len(m.path)):
            r.append(asdict(m))
        return r

    def _get_system_mounted_disks(self):
        # This assumes a fairly vanilla setup. It won't list as
        # mounted a disk that is only mounted via lvm, for example.
        mounted_devs = []
        with open('/proc/mounts', encoding=sys.getfilesystemencoding()) as pm:
            for line in pm:
                if line.startswith('/dev/'):
                    mounted_devs.append(line.split()[0][5:])
        mounted_disks = set()
        for dev in mounted_devs:
            if os.path.exists('/sys/block/{}'.format(dev)):
                mounted_disks.add('/dev/' + dev)
            else:
                paths = glob.glob('/sys/block/*/{}/partition'.format(dev))
                if len(paths) == 1:
                    mounted_disks.add('/dev/' + paths[0].split('/')[3])
        return mounted_disks

    def probe(self):
        storage = self.prober.get_storage()
        currently_mounted = self._get_system_mounted_disks()
        for path, data in storage.items():
            log.debug("fs probe %s", path)
            if path in currently_mounted:
                continue
            if data['DEVTYPE'] == 'disk':
                if data["DEVPATH"].startswith('/devices/virtual'):
                    continue
                if data["MAJOR"] in ("2", "11"):  # serial and cd devices
                    continue
                if data['attrs'].get('ro') == "1":
                    continue
                if "ID_CDROM" in data:
                    continue
                # log.debug('disk={}\n{}'.format(
                #    path, json.dumps(data, indent=4, sort_keys=True)))
                info = self.prober.get_storage_info(path)
                if info.size < self.lower_size_limit:
                    continue
                self._available_disks[path] = Disk.from_info(info)

    def _use_disk(self, disk):
        if disk.path not in self._disks:
            self._disks[disk.path] = disk

    def all_mounts(self):
        return self._mounts[:]

    def all_disks(self):
        return sorted(self._available_disks.values(), key=lambda x: x.label)

    def all_raids(self):
        return self._raids[:]

    def all_devices(self):
        return self.all_disks() + self.all_raids()  # + self.all_lvms() + ...

    def get_disk(self, path):
        return self._available_disks.get(path)

    def add_partition(self, disk, size, flag=""):
        if size > disk.free_for_partitions:
            raise Exception("%s > %s", size, disk.free_for_partitions)
        real_size = align_up(size)
        log.debug("add_partition: rounded size from %s to %s", size, real_size)
        if isinstance(disk, Disk):
            self._use_disk(disk)
        if disk._fs is not None:
            raise Exception("%s is already formatted" % (disk.path,))
        p = Partition(device=disk, size=real_size, flag=flag)
        if flag in ("boot", "bios_grub"):
            disk._partitions.insert(0, p)
        else:
            disk._partitions.append(p)
        disk.ptable = 'gpt'
        self._partitions.append(p)
        return p

    def remove_partition(self, part):
        if part._fs or part._constructed_device:
            raise Exception("can only remove empty partition")
        part.device._partitions.remove(part)
        self._partitions.remove(part)
        if len(part.device._partitions) == 0:
            part.device.ptable = None

    def add_raid(self, name, raidlevel, devices, spare_devices):
        r = Raid(
            name=name,
            raidlevel=raidlevel,
            devices=devices,
            spare_devices=spare_devices)
        for d in devices | spare_devices:
            if isinstance(d, Disk):
                self._use_disk(d)
            d._constructed_device = r
        self._raids.append(r)
        return r

    def remove_raid(self, raid):
        if raid._fs or raid._constructed_device or len(raid.partitions()):
            raise Exception("can only remove empty RAID")
        for d in raid.devices:
            d._constructed_device = None
        self._raids.remove(raid)

    def add_filesystem(self, volume, fstype):
        log.debug("adding %s to %s", fstype, volume)
        if not volume.available:
            if not isinstance(volume, Partition):
                if (volume.flag == 'bios_grub' and fstype == 'fat32'):
                    raise Exception("{} is not available".format(volume))
        if isinstance(volume, Disk):
            self._use_disk(volume)
        if volume._fs is not None:
            raise Exception("%s is already formatted")
        volume._fs = fs = Filesystem(volume=volume, fstype=fstype)
        self._filesystems.append(fs)
        return fs

    def remove_filesystem(self, fs):
        if fs._mount:
            raise Exception("can only remove unmounted filesystem")
        fs.volume._fs = None
        self._filesystems.remove(fs)

    def add_mount(self, fs, path):
        if fs._mount is not None:
            raise Exception("%s is already mounted")
        fs._mount = m = Mount(device=fs, path=path)
        self._mounts.append(m)
        return m

    def remove_mount(self, mount):
        mount.device._mount = None
        self._mounts.remove(mount)

    def get_mountpoint_to_devpath_mapping(self):
        r = {}
        for m in self._mounts:
            if isinstance(m.device.volume, Raid):
                r[m.path] = m.device.volume.name
            else:
                r[m.path] = m.device.volume.path
        return r

    def any_configuration_done(self):
        return len(self._disks) > 0

    def can_install(self):
        # Do we need to check that there is a disk with the boot flag?
        return ('/' in self.get_mountpoint_to_devpath_mapping() and
                self.bootable())

    def bootable(self):
        ''' true if one disk has a boot partition '''
        for p in self._partitions:
            if p.flag == 'bios_grub' or p.flag == 'boot':
                return True
        return False

    def add_swapfile(self):
        for m in self._mounts:
            if m.path == '/':
                if m.device.fstype == 'btrfs':
                    return False
        for fs in self._filesystems:
            if fs.fstype == "swap":
                return False
        return True
