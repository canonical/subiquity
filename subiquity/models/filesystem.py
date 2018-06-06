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

import attr
import collections
import glob
import logging
import math
import os
import sys

HUMAN_UNITS = ['B', 'K', 'M', 'G', 'T', 'P']
log = logging.getLogger('subiquity.models.filesystem')


@attr.s
class FS:
    label = attr.ib()
    is_mounted = attr.ib()


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
        if v:
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


@attr.s
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


@attr.s
class _Device(_Formattable):
    # Anything that can have partitions, e.g. a disk or a RAID.

    # subclass must implement .size!

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
    def free(self):
        return self.size - self.used

    def available(self):
        # A _Device is available if:
        # 1) it is not part of a RAID (or LVM or zpool or ...)
        # 2) if it is formatted, it is available if it is formatted with fs
        #    that needs to be mounted and is not mounted
        # 3) if it is not formatted, if is available if it has free
        #    space OR at least one partition is not formatted or is formatted
        #    with a fs that needs to be mounted and is not mounted
        if self._constructed_device is not None:
            return False
        if self._fs is not None:
            return self._fs._available()
        if self.free > 0:
            return True
        for p in self._partitions:
            if p.available():
                return True
        return False


@attr.s
class Disk(_Device):

    id = attr.ib(default=id_factory("disk"))
    type = attr.ib(default="disk")
    ptable = attr.ib(default='gpt')
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
        self.grub_device = ''
        self._partitions = []
        self._fs = None
        self._constructed_device = None

    @property
    def size(self):
        # The first and last megabyte of the disk are not usable.
        return max(0, align_down(self._info.size) - (2 << 20))

    def desc(self):
        return _("local disk")

    @property
    def label(self):
        if self.serial is not None:
            return self.serial
        return self.path


@attr.s
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

    @property
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


@attr.s
class Raid(_Device):
    id = attr.ib(default=id_factory("raid"))
    type = attr.ib(default="raid")
    name = attr.ib(default=None)
    raidlevel = attr.ib(default=None)  # 0, 1, 5, 6, 10
    devices = attr.ib(default=attr.Factory(list))  # [_Formattable]

    @property
    def size(self):
        return get_raid_size(self.raidlevel, self.devices)

    @property
    def label(self):
        return self.name

    def desc(self):
        return _("software RAID {}").format(self.raidlevel)


@attr.s
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
            fs_obj = FilesystemModel.fs_by_name[self._fs.fstype]
            return fs_obj.is_mounted
        else:
            return False


@attr.s
class Mount:
    id = attr.ib(default=id_factory("mount"))
    type = attr.ib(default="mount")
    device = attr.ib(default=None)  # Filesystem
    path = attr.ib(default=None)


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
        for f in self._filesystems:
            if f.fstype == 'swap':
                if isinstance(f.volume, Partition):
                    f.volume.flag = "swap"
                if f.mount() is None:
                    self.add_mount(f, "")
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
                if not data["DEVPATH"].startswith('/devices/virtual'):
                    if data["MAJOR"] != "2" and data['attrs'].get('ro') != "1":
                        #  log.debug('disk={}\n{}'.format(
                        #    path, json.dumps(data, indent=4, sort_keys=True)))
                        info = self.prober.get_storage_info(path)
                        self._available_disks[path] = Disk.from_info(info)

    def _use_disk(self, disk):
        if disk.path not in self._disks:
            self._disks[disk.path] = disk

    def all_disks(self):
        return sorted(self._available_disks.values(), key=lambda x: x.label)

    def all_raids(self):
        return self._raids

    def all_devices(self):
        return self.all_disks() + self.all_raids()  # + self.all_lvms() + ...

    def get_disk(self, path):
        return self._available_disks.get(path)

    def add_partition(self, disk, size, flag=""):
        if size > disk.free:
            raise Exception("%s > %s", size, disk.free)
        real_size = align_up(size)
        log.debug("add_partition: rounded size from %s to %s", size, real_size)
        self._use_disk(disk)
        if disk._fs is not None:
            raise Exception("%s is already formatted" % (disk.path,))
        p = Partition(device=disk, size=real_size, flag=flag)
        disk._partitions.append(p)
        self._partitions.append(p)
        return p

    def add_raid(self, result):
        r = Raid(
            name=result['name'],
            raidlevel=result['level'].value,
            devices=result['devices'])
        for d in result['devices']:
            if isinstance(d, Disk):
                self._use_disk(d)
            d._raid = r
        self._raids.append(r)
        return r

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

    def add_mount(self, fs, path):
        if fs._mount is not None:
            raise Exception("%s is already mounted")
        fs._mount = m = Mount(device=fs, path=path)
        self._mounts.append(m)
        return m

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
