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
import platform

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


# This is a guess!
RAID_OVERHEAD = 8 * (1 << 20)


def get_raid_size(level, devices):
    if len(devices) == 0:
        return 0
    min_size = min(dev.size for dev in devices) - RAID_OVERHEAD
    if min_size <= 0:
        return 0
    if level == 0:
        return min_size * len(devices)
    elif level == 1:
        return min_size
    elif level == 5:
        return (min_size - RAID_OVERHEAD) * (len(devices) - 1)
    elif level == 6:
        return (min_size - RAID_OVERHEAD) * (len(devices) - 2)
    elif level == 10:
        return min_size * (len(devices) // 2)
    else:
        raise ValueError("unknown raid level %s" % level)


# These are only defaults but curtin does not let you change/specify
# them at this time.
LVM_OVERHEAD = (1 << 20)
LVM_CHUNK_SIZE = 4 * (1 << 20)


def get_lvm_size(devices, size_overrides={}):
    r = 0
    for d in devices:
        r += align_down(
            size_overrides.get(d, d.size) - LVM_OVERHEAD,
            LVM_CHUNK_SIZE)
    return r


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
        v = getattr(
            inst,
            'serialize_' + field.name,
            lambda: getattr(inst, field.name))()
        if v is not None:
            p = ''
            if getattr(inst, '_passphrase', None) is not None:
                p = 'dm-'
            if isinstance(v, (list, set)):
                r[field.name] = [p + elem.id for elem in v]
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
    INFO = _("Info")
    EDIT = _("Edit")
    PARTITION = _("Add Partition")
    CREATE_LV = _("Create Logical Volume")
    FORMAT = _("Format")
    REMOVE = _("Remove from RAID/LVM")
    DELETE = _("Delete")
    MAKE_BOOT = _("Make Boot Device")


def _generic_can_EDIT(obj):
    cd = obj.constructed_device()
    if cd is None:
        return True
    return _(
        "Cannot edit {selflabel} as it is part of the {cdtype} "
        "{cdname}.").format(
            selflabel=obj.label,
            cdtype=cd.desc(),
            cdname=cd.label)


def _generic_can_REMOVE(obj):
    cd = obj.constructed_device()
    if cd is None:
        return False
    if isinstance(cd, Raid):
        if obj in cd.spare_devices:
            return True
        min_devices = raidlevels_by_value[cd.raidlevel].min_devices
        if len(cd.devices) == min_devices:
            return _(
                "Removing {selflabel} would leave the {cdtype} {cdlabel} with "
                "less than {min_devices} devices.").format(
                    selflabel=obj.label,
                    cdtype=cd.desc(),
                    cdlabel=cd.label,
                    min_devices=min_devices)
    elif isinstance(cd, LVM_VolGroup):
        if len(cd.devices) == 1:
            return _(
                "Removing {selflabel} would leave the {cdtype} {cdlabel} with "
                "no devices.").format(
                    selflabel=obj.label,
                    cdtype=cd.desc(),
                    cdlabel=cd.label)
    return True


def _generic_can_DELETE(obj):
    cd = obj.constructed_device()
    if cd is None:
        return True
    return _(
        "Cannot delete {selflabel} as it is part of the {cdtype} "
        "{cdname}.").format(
            selflabel=obj.label,
            cdtype=cd.desc(),
            cdname=cd.label)


@attr.s(cmp=False)
class _Formattable(ABC):
    # Base class for anything that can be formatted and mounted,
    # e.g. a disk or a RAID or a partition.

    # Filesystem
    _fs = attr.ib(default=None, repr=False)
    # Raid or LVM_VolGroup for now, but one day ZPool, BCache...
    _constructed_device = attr.ib(default=None, repr=False)

    def _is_entirely_used(self):
        return self._fs is not None or self._constructed_device is not None

    def fs(self):
        return self._fs

    def constructed_device(self):
        return self._constructed_device

    @property
    @abstractmethod
    def supported_actions(self):
        pass

    def action_possible(self, action):
        assert action in self.supported_actions
        r = getattr(self, "_can_" + action.name)
        if isinstance(r, bool):
            return r, None
        elif isinstance(r, str):
            return False, r
        else:
            return r

    @property
    @abstractmethod
    def ok_for_raid(self):
        pass

    @property
    @abstractmethod
    def ok_for_lvm_vg(self):
        pass


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

    supported_actions = [
        DeviceAction.INFO,
        DeviceAction.PARTITION,
        DeviceAction.FORMAT,
        DeviceAction.REMOVE,
        ]
    if platform.machine() != 's390x':
        supported_actions.append(DeviceAction.MAKE_BOOT)
    _can_INFO = True
    _can_PARTITION = property(lambda self: self.free_for_partitions > 0)
    _can_FORMAT = property(
        lambda self: len(self._partitions) == 0 and
        self._constructed_device is None)
    _can_REMOVE = property(_generic_can_REMOVE)
    _can_MAKE_BOOT = property(
        lambda self:
        not self.grub_device and self._fs is None
        and self._constructed_device is None)

    ok_for_raid = ok_for_lvm_vg = _can_FORMAT


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

    @property
    def short_label(self):
        return _("partition {}").format(self._number)

    def available(self):
        if self.flag in ['bios_grub', 'prep']:
            return False
        if self._constructed_device is not None:
            return False
        if self._fs is None:
            return True
        return self._fs._available()

    @property
    def _number(self):
        return self.device._partitions.index(self) + 1

    supported_actions = [
        DeviceAction.EDIT,
        DeviceAction.REMOVE,
        DeviceAction.DELETE,
        ]

    _can_EDIT = property(_generic_can_EDIT)
    _can_REMOVE = property(_generic_can_REMOVE)

    @property
    def _can_DELETE(self):
        if self.flag in ('boot', 'bios_grub', 'prep'):
            return _("Cannot delete required bootloader partition")
        return _generic_can_DELETE(self)

    @property
    def ok_for_raid(self):
        if self.flag:
            return False
        if self._fs is not None:
            return False
        if self._constructed_device is not None:
            return False
        return True

    ok_for_lvm_vg = ok_for_raid


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
    def free_for_partitions(self):
        # For some reason, the overhead on RAID devices seems to be
        # higher (may be related to alignment of underlying
        # partitions)
        return self.size - self.used - 2*GPT_OVERHEAD

    @property
    def label(self):
        return self.name

    def desc(self):
        return _("software RAID {}").format(self.raidlevel)

    supported_actions = [
        DeviceAction.EDIT,
        DeviceAction.PARTITION,
        DeviceAction.FORMAT,
        DeviceAction.REMOVE,
        DeviceAction.DELETE,
        ]

    @property
    def _can_EDIT(self):
        if len(self._partitions) > 0:
            return _(
                "Cannot edit {selflabel} because it has partitions.").format(
                    selflabel=self.label)
        else:
            return _generic_can_EDIT(self)

    _can_PARTITION = Disk._can_PARTITION
    _can_FORMAT = property(
        lambda self: len(self._partitions) == 0 and
        self._constructed_device is None)
    _can_REMOVE = property(_generic_can_REMOVE)

    @property
    def _can_DELETE(self):
        if len(self._partitions) > 0:
            return _(
                "Cannot delete {selflabel} because it has partitions.").format(
                    selflabel=self.label)
        else:
            return _generic_can_DELETE(self)

    @property
    def ok_for_raid(self):
        if self._fs is not None:
            return False
        if len(self._partitions) > 0:
            return False
        if self._constructed_device is not None:
            return False
        return True

    ok_for_lvm_vg = ok_for_raid

    # What is a device that makes up this device referred to as?
    component_name = "component"


LUKS_OVERHEAD = 16*(2**20)


@attr.s(cmp=False)
class LVM_VolGroup(_Device):

    id = attr.ib(default=id_factory("vg"))
    type = attr.ib(default="lvm_volgroup")
    name = attr.ib(default=None)
    devices = attr.ib(default=attr.Factory(set))  # set([_Formattable])
    _passphrase = attr.ib(default=None, repr=False)

    @property
    def size(self):
        size = get_lvm_size(self.devices)
        if self._passphrase:
            size -= LUKS_OVERHEAD
        return size

    @property
    def free_for_partitions(self):
        return self.size - self.used

    @property
    def label(self):
        return self.name

    def desc(self):
        return "LVM volume group"

    supported_actions = [
        DeviceAction.EDIT,
        DeviceAction.CREATE_LV,
        DeviceAction.DELETE,
        ]

    @property
    def _can_EDIT(self):
        if len(self._partitions) > 0:
            return _(
                "Cannot edit {selflabel} because it has logical "
                "volumes.").format(
                    selflabel=self.label)
        else:
            return _generic_can_EDIT(self)

    _can_CREATE_LV = Disk._can_PARTITION

    @property
    def _can_DELETE(self):
        if len(self._partitions) > 0:
            return _(
                "Cannot delete {selflabel} because it has logical "
                "volumes.").format(
                    selflabel=self.label)
        else:
            return _generic_can_DELETE(self)

    ok_for_raid = False
    ok_for_lvm_vg = False

    # What is a device that makes up this device referred to as?
    component_name = "PV"


@attr.s(cmp=False)
class LVM_LogicalVolume(_Formattable):

    id = attr.ib(default=id_factory("lv"))
    type = attr.ib(default="lvm_partition")
    name = attr.ib(default=None)
    volgroup = attr.ib(default=None)  # LVM_VolGroup
    size = attr.ib(default=None)

    def serialize_size(self):
        return "{}b".format(self.size)

    def available(self):
        if self._constructed_device is not None:
            return False
        return True

    @property
    def flag(self):
        return None  # hack!

    def desc(self):
        return "LVM logical volume"

    @property
    def short_label(self):
        return self.name

    label = short_label

    supported_actions = [
        DeviceAction.EDIT,
        DeviceAction.DELETE,
        ]

    _can_EDIT = True
    _can_DELETE = True

    ok_for_raid = False
    ok_for_lvm_vg = False


@attr.s(cmp=False)
class DM_Crypt:
    id = attr.ib(default=id_factory("crypt"))
    type = attr.ib(default="dm_crypt")
    dm_name = attr.ib(default=None)
    volume = attr.ib(default=None)  # _Formattable
    key = attr.ib(default=None)


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
        self._vgs = []
        self._lvs = []
        self._filesystems = []
        self._mounts = []
        for k, d in self._available_disks.items():
            self._available_disks[k].reset()

    def render(self):
        # the curtin storage config has the constraint that an action
        # must be preceded by all the things that it depends on. Disks
        # are easy because they don't depend on anything, but a raid
        # can both be built of partitions and be partitioned itself so
        # in some cases raid and partition actions have to be
        # intermingled. We tackle this by tracking the ids that have
        # been emitted and iterating over the raid and partition
        # objects and emitting the ones that can be emitted repeatedly
        # until there are none left (or we make no progress, which
        # means there is a cycle in the definitions, something the UI
        # should have prevented <wink>)
        r = []
        emitted_ids = set()

        def emit(obj):
            r.append(asdict(obj))
            emitted_ids.add(obj.id)

        # As mentioned disks are easy.
        for d in self._disks.values():
            emit(d)

        def can_emit(obj):
            # This will need to be extended for things like bcache
            if isinstance(obj, Partition):
                return obj.device.id in emitted_ids
            elif isinstance(obj, Raid):
                for device in obj.devices | obj.spare_devices:
                    if device.id not in emitted_ids:
                        return False
                return True
            elif isinstance(obj, LVM_VolGroup):
                p = ''
                if obj._passphrase:
                    p = "dm-"
                for device in obj.devices:
                    if p + device.id not in emitted_ids:
                        return False
                return True
            elif isinstance(obj, LVM_LogicalVolume):
                return obj.volgroup.id in emitted_ids
            elif isinstance(obj, DM_Crypt):
                return obj.volume.id in emitted_ids
            else:
                raise Exception(
                    "don't know how to decide if {} can be emitted".format(
                        obj))

        dms = []
        for vg in self._vgs:
            if vg._passphrase:
                for volume in vg.devices:
                    dms.append(DM_Crypt(
                        id="dm-" + volume.id,
                        volume=volume,
                        key=vg._passphrase))

        work = self._partitions + self._raids + dms + self._vgs + self._lvs

        while work:
            next_work = []
            for obj in work:
                if can_emit(obj):
                    emit(obj)
                else:
                    next_work.append(obj)
            if len(next_work) == len(work):
                raise Exception(
                    "rendering block devices made no progress: {}".format(
                        work))
            work = next_work

        # Filesystems and mounts are also easy, dependencies only flow
        # from mounts to filesystems to things already emitted.
        for f in self._filesystems:
            emit(f)

        for m in sorted(self._mounts, key=lambda m: len(m.path)):
            emit(m)

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

    def all_volgroups(self):
        return self._vgs[:]

    def all_devices(self):
        return self.all_disks() + self.all_raids() + self.all_volgroups()

    def add_partition(self, disk, size, wipe=None, flag=""):
        if size > disk.free_for_partitions:
            raise Exception("%s > %s", size, disk.free_for_partitions)
        real_size = align_up(size)
        log.debug("add_partition: rounded size from %s to %s", size, real_size)
        if isinstance(disk, Disk):
            self._use_disk(disk)
        if disk._fs is not None:
            raise Exception("%s is already formatted" % (disk.label,))
        p = Partition(device=disk, size=real_size, wipe=wipe, flag=flag)
        if flag in ("boot", "bios_grub", "prep"):
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

    def add_volgroup(self, name, devices, passphrase):
        vg = LVM_VolGroup(name=name, devices=devices, passphrase=passphrase)
        for d in devices:
            if isinstance(d, Disk):
                self._use_disk(d)
            d._constructed_device = vg
        self._vgs.append(vg)
        return vg

    def remove_volgroup(self, vg):
        if len(vg._partitions):
            raise Exception("can only remove empty VG")
        for d in vg.devices:
            d._constructed_device = None
        self._vgs.remove(vg)

    def add_logical_volume(self, vg, name, size):
        lv = LVM_LogicalVolume(volgroup=vg, name=name, size=size)
        vg._partitions.append(lv)
        self._lvs.append(lv)
        return lv

    def remove_logical_volume(self, lv):
        if lv._fs:
            raise Exception("can only remove empty LV")
        lv.volgroup._partitions.remove(lv)
        self._lvs.remove(lv)

    def add_filesystem(self, volume, fstype):
        log.debug("adding %s to %s", fstype, volume)
        if not volume.available:
            if not isinstance(volume, Partition):
                if (volume.flag == 'prep' or (
                        volume.flag == 'bios_grub' and fstype == 'fat32')):
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

    def any_configuration_done(self):
        return len(self._disks) > 0

    def needs_bootloader_partition(self):
        '''true if no disk have a boot partition, and one is needed'''
        # s390x has no such thing
        if platform.machine() == 's390x':
            return False
        for p in self._partitions:
            if p.flag in ('bios_grub', 'boot', 'prep'):
                return False
        return True

    def is_root_mounted(self):
        for mount in self._mounts:
            if mount.path == '/':
                return True
        return False

    def is_slash_boot_on_local_disk(self):
        for mount in self._mounts:
            if mount.path == '/boot':
                dev = mount.device.volume
                # We should never allow anything other than a
                # partition of a local disk to be mounted at /boot but
                # well.
                return (
                    isinstance(dev, Partition)
                    and isinstance(dev.device, Disk))
        for mount in self._mounts:
            if mount.path == '/':
                dev = mount.device.volume
                return (
                    isinstance(dev, Partition)
                    and isinstance(dev.device, Disk))
        return False

    def can_install(self):
        # Do we need to check that there is a disk with the boot flag?
        return (self.is_root_mounted()
                and not self.needs_bootloader_partition()
                and self.is_slash_boot_on_local_disk())

    def add_swapfile(self):
        for m in self._mounts:
            if m.path == '/':
                if m.device.fstype == 'btrfs':
                    return False
        for fs in self._filesystems:
            if fs.fstype == "swap":
                return False
        return True
