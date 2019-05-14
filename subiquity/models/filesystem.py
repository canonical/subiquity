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
import pathlib
import platform
import sys

log = logging.getLogger('subiquity.models.filesystem')


def _set_backlinks(obj):
    for field in attr.fields(type(obj)):
        backlink = field.metadata.get('backlink')
        if backlink is None:
            continue
        v = getattr(obj, field.name)
        if v is None:
            continue
        if not isinstance(v, (list, set)):
            v = [v]
        for vv in v:
            b = getattr(vv, backlink, None)
            if isinstance(b, list):
                b.append(obj)
            elif isinstance(b, set):
                b.add(obj)
            else:
                setattr(vv, backlink, obj)


def _remove_backlinks(obj):
    for field in attr.fields(type(obj)):
        backlink = field.metadata.get('backlink')
        if backlink is None:
            continue
        v = getattr(obj, field.name)
        if v is None:
            continue
        if not isinstance(v, (list, set)):
            v = [v]
        for vv in v:
            b = getattr(vv, backlink, None)
            if isinstance(b, list):
                b.remove(obj)
            elif isinstance(b, set):
                b.remove(obj)
            else:
                setattr(vv, backlink, None)


def fsobj(c):
    c.__attrs_post_init__ = _set_backlinks
    c._m = attr.ib(default=None)
    return attr.s(cmp=False)(c)


def dependencies(obj):
    for f in attr.fields(type(obj)):
        v = getattr(obj, f.name)
        if not v:
            continue
        elif f.metadata.get('ref', False):
            yield v
        elif f.metadata.get('reflist', False):
            yield from v


@attr.s(cmp=False)
class RaidLevel:
    name = attr.ib()
    value = attr.ib()
    min_devices = attr.ib()
    supports_spares = attr.ib(default=True)


raidlevels = [
    RaidLevel(_("0 (striped)"),  "raid0",  2, False),
    RaidLevel(_("1 (mirrored)"), "raid1",  2),
    RaidLevel(_("5"),            "raid5",  3),
    RaidLevel(_("6"),            "raid6",  4),
    RaidLevel(_("10"),           "raid10", 4),
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
    if level == "raid0":
        return min_size * len(devices)
    elif level == "raid1":
        return min_size
    elif level == "raid5":
        return (min_size - RAID_OVERHEAD) * (len(devices) - 1)
    elif level == "raid6":
        return (min_size - RAID_OVERHEAD) * (len(devices) - 2)
    elif level == "raid10":
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


def idfield(base):
    i = 0

    def factory():
        nonlocal i
        r = "%s-%s" % (base, i)
        i += 1
        return r
    return attr.ib(default=attr.Factory(factory))


def ref(*, backlink=None):
    metadata = {'ref': True}
    if backlink:
        metadata['backlink'] = backlink
    return attr.ib(default=None, metadata=metadata)


def reflist(*, backlink=None):
    metadata = {'reflist': True}
    if backlink:
        metadata['backlink'] = backlink
    return attr.ib(default=attr.Factory(set), metadata=metadata)


def const(value):
    return attr.ib(default=value)


def asdict(inst):
    r = collections.OrderedDict()
    for field in attr.fields(type(inst)):
        if field.name.startswith('_'):
            continue
        m = getattr(inst, 'serialize_' + field.name, None)
        if m:
            r[field.name] = m()
        else:
            v = getattr(inst, field.name)
            if v is not None:
                if field.metadata.get('ref', False):
                    r[field.name] = v.id
                elif field.metadata.get('reflist', False):
                    r[field.name] = [elem.id for elem in v]
                else:
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

    @property
    @abstractmethod
    def label(self):
        pass

    @property
    def annotations(self):
        return []

    # Filesystem
    _fs = attr.ib(default=None, repr=False)
    # Raid or LVM_VolGroup for now, but one day ZPool, BCache...
    _constructed_device = attr.ib(default=None, repr=False)

    def _is_entirely_used(self):
        return self._fs is not None or self._constructed_device is not None

    def fs(self):
        return self._fs

    def constructed_device(self, skip_dm_crypt=True):
        cd = self._constructed_device
        if cd is None:
            return None
        elif cd.type == "dm_crypt" and skip_dm_crypt:
            return cd._constructed_device
        else:
            return cd

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

    @property
    def _can_DELETE(self):
        mounted_partitions = 0
        for p in self._partitions:
            if p.fs() and p.fs().mount():
                mounted_partitions += 1
            elif p.constructed_device():
                cd = p.constructed_device()
                return _(
                    "Cannot delete {selflabel} as partition {partnum} is part "
                    "of the {cdtype} {cdname}.").format(
                        selflabel=self.label,
                        partnum=p._number,
                        cdtype=cd.desc(),
                        cdname=cd.label,
                        )
        if mounted_partitions > 1:
            return _(
                "Cannot delete {selflabel} because it has {count} mounted "
                "partitions.").format(
                    selflabel=self.label,
                    count=mounted_partitions)
        elif mounted_partitions == 1:
            return _(
                "Cannot delete {selflabel} because it has 1 mounted partition."
                ).format(selflabel=self.label)
        else:
            return _generic_can_DELETE(self)


@fsobj
class Disk(_Device):

    id = idfield("disk")
    type = const("disk")
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
    def from_info(self, model, info):
        d = Disk(m=model, info=info)
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

    @property
    def supported_actions(self):
        actions = [
            DeviceAction.INFO,
            DeviceAction.PARTITION,
            DeviceAction.FORMAT,
            DeviceAction.REMOVE,
            ]
        if self._m.bootloader != Bootloader.NONE:
            actions.append(DeviceAction.MAKE_BOOT)
        return actions

    _can_INFO = True
    _can_PARTITION = property(lambda self: self.free_for_partitions > 0)
    _can_FORMAT = property(
        lambda self: len(self._partitions) == 0 and
        self._constructed_device is None)
    _can_REMOVE = property(_generic_can_REMOVE)

    @property
    def _can_MAKE_BOOT(self):
        install_dev = self._m.grub_install_device
        if install_dev:
            # For the PReP case, the install_device is the prep partition.
            if install_dev.type == "partition":
                install_dev = install_dev.device
            if install_dev is self:
                return False
        return self._fs is None and self._constructed_device is None

    ok_for_raid = ok_for_lvm_vg = _can_FORMAT


@fsobj
class Partition(_Formattable):

    id = idfield("part")
    type = const("partition")
    device = ref(backlink="_partitions")  # Disk
    size = attr.ib(default=None)
    wipe = attr.ib(default=None)
    flag = attr.ib(default=None)
    preserve = attr.ib(default=False)

    @property
    def annotations(self):
        r = super().annotations
        if self.flag == "prep":
            r.append("PReP")
        elif self.flag == "boot":
            r.append("ESP")
        elif self.flag == "bios_grub":
            r.append("bios_grub")
        return r

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
        if self.flag in ('boot', 'bios_grub', 'prep'):
            return False
        if self._fs is not None:
            return False
        if self._constructed_device is not None:
            return False
        return True

    ok_for_lvm_vg = ok_for_raid


@fsobj
class Raid(_Device):
    id = idfield("raid")
    type = const("raid")
    preserve = attr.ib(default=False)
    name = attr.ib(default=None)
    raidlevel = attr.ib(default=None)  # raid0, raid1, raid5, raid6, raid10
    devices = reflist(backlink="_constructed_device")  # set([_Formattable])
    spare_devices = reflist(backlink="_constructed_device")  # ditto
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
        return _("software RAID {}").format(self.raidlevel[4:])

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


@fsobj
class LVM_VolGroup(_Device):

    id = idfield("vg")
    type = const("lvm_volgroup")
    preserve = attr.ib(default=False)
    name = attr.ib(default=None)
    devices = reflist(backlink="_constructed_device")  # set([_Formattable])

    @property
    def size(self):
        return get_lvm_size(self.devices)

    @property
    def free_for_partitions(self):
        return self.size - self.used

    @property
    def annotations(self):
        r = super().annotations
        member = next(iter(self.devices))
        if member.type == "dm_crypt":
            r.append("encrypted")
        return r

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

    ok_for_raid = False
    ok_for_lvm_vg = False

    # What is a device that makes up this device referred to as?
    component_name = "PV"


@fsobj
class LVM_LogicalVolume(_Formattable):

    id = idfield("lv")
    type = const("lvm_partition")
    name = attr.ib(default=None)
    volgroup = ref(backlink="_partitions")  # LVM_VolGroup
    size = attr.ib(default=None)
    preserve = attr.ib(default=False)

    def serialize_size(self):
        return "{}B".format(self.size)

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


LUKS_OVERHEAD = 16*(2**20)


@fsobj
class DM_Crypt:
    id = idfield("crypt")
    type = const("dm_crypt")
    dm_name = attr.ib(default=None)
    volume = ref(backlink="_constructed_device")  # _Formattable
    key = attr.ib(default=None, repr=False)
    preserve = attr.ib(default=False)

    _constructed_device = attr.ib(default=None, repr=False)

    def constructed_device(self):
        return self._constructed_device

    @property
    def size(self):
        return self.volume.size - LUKS_OVERHEAD


@fsobj
class Filesystem:

    id = idfield("fs")
    type = const("format")
    fstype = attr.ib(default=None)
    volume = ref(backlink="_fs")  # _Formattable
    label = attr.ib(default=None)
    uuid = attr.ib(default=None)
    preserve = attr.ib(default=False)

    _mount = attr.ib(default=None, repr=False)  # Mount

    def mount(self):
        return self._mount

    def _available(self):
        # False if mounted or if fs does not require a mount, True otherwise.
        if self._mount is None:
            return FilesystemModel.is_mounted_filesystem(self.fstype)
        else:
            return False


@fsobj
class Mount:
    id = idfield("mount")
    type = const("mount")
    device = ref(backlink="_mount")  # Filesystem
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


class Bootloader(enum.Enum):
    NONE = "NONE"  # a system where the bootloader is external, e.g. s390x
    BIOS = "BIOS"  # BIOS, where the bootloader dd-ed to the start of a device
    UEFI = "UEFI"  # UEFI, ESPs and /boot/efi and all that (amd64 and arm64)
    PREP = "PREP"  # ppc64el, which puts grub on a PReP partition


class FilesystemModel(object):

    lower_size_limit = 128 * (1 << 20)

    @classmethod
    def is_mounted_filesystem(self, fstype):
        if fstype in [None, 'swap']:
            return False
        else:
            return True

    def _probe_bootloader(self):
        # This will at some point change to return a list so that we can
        # configure BIOS _and_ UEFI on amd64 systems.
        if os.path.exists('/sys/firmware/efi'):
            return Bootloader.UEFI
        elif platform.machine().startswith("ppc64"):
            return Bootloader.PREP
        elif platform.machine() == "s390x":
            return Bootloader.NONE
        else:
            return Bootloader.BIOS

    def __init__(self):
        self.bootloader = self._probe_bootloader()
        self._disk_info = []
        self.reset()

    def reset(self):
        self._actions = [
            Disk.from_info(self, info) for info in self._disk_info]
        self.grub_install_device = None

    def _render_actions(self):
        # The curtin storage config has the constraint that an action must be
        # preceded by all the things that it depends on.  We handle this by
        # repeatedly iterating over all actions and checking if we can emit
        # each action by checking if all of the actions it depends on have been
        # emitted.  Eventually this will either emit all actions or stop making
        # progress -- which means there is a cycle in the definitions,
        # something the UI should have prevented <wink>.
        r = []
        emitted_ids = set()

        def emit(obj):
            if obj.type == 'disk' and not obj.used:
                return
            r.append(asdict(obj))
            emitted_ids.add(obj.id)

        def can_emit(obj):
            for dep in dependencies(obj):
                if dep.id not in emitted_ids:
                    return False
            if isinstance(obj, Mount):
                # Any mount actions for a parent of this one have to be emitted
                # first.
                for parent in pathlib.Path(obj.path).parents:
                    parent = str(parent)
                    if parent in mountpoints:
                        if mountpoints[parent] not in emitted_ids:
                            log.debug(
                                "cannot emit action to mount %s until that "
                                "for %s is emitted", obj.path, parent)
                            return False
            return True

        mountpoints = {m.path: m.id for m in self.all_mounts()}
        log.debug('mountpoints %s', mountpoints)

        work = self._actions[:]

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

        return r

    def render(self):
        config = {
            'storage': {
                'version': 1,
                'config': self._render_actions(),
                },
            }
        if not self._should_add_swapfile():
            config['swap'] = {'size': 0}
        if self.grub_install_device:
            dev = self.grub_install_device
            if dev.type == "partition":
                devpath = "{}{}".format(dev.device.path, dev._number)
            else:
                devpath = dev.path
            config['grub'] = {
                'install_devices': [devpath],
                }
        return config

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

    def load_probe_data(self, storage):
        currently_mounted = self._get_system_mounted_disks()
        for path, info in storage.items():
            log.debug("fs probe %s", path)
            if path in currently_mounted:
                continue
            if info.type == 'disk':
                if info.is_virtual:
                    continue
                if info.raw["MAJOR"] in ("2", "11"):  # serial and cd devices
                    continue
                if info.raw['attrs'].get('ro') == "1":
                    continue
                if "ID_CDROM" in info.raw:
                    continue
                # log.debug('disk={}\n{}'.format(
                #    path, json.dumps(data, indent=4, sort_keys=True)))
                if info.size < self.lower_size_limit:
                    continue
                self._disk_info.append(info)
                self._actions.append(Disk.from_info(self, info))

    def disk_by_path(self, path):
        for a in self._actions:
            if a.type == 'disk' and a.path == path:
                return a
        raise KeyError("no disk with path {} found".format(path))

    def all_filesystems(self):
        return [a for a in self._actions if a.type == 'format']

    def all_mounts(self):
        return [a for a in self._actions if a.type == 'mount']

    def all_devices(self):
        # return:
        #  compound devices, newest first
        #  disk devices, sorted by label
        disks = []
        compounds = []
        for a in self._actions:
            if a.type == 'disk':
                disks.append(a)
            elif isinstance(a, _Device):
                compounds.append(a)
        compounds.reverse()
        disks.sort(key=lambda x: x.label)
        return compounds + disks

    def all_partitions(self):
        return [a for a in self._actions if a.type == 'partition']

    def all_disks(self):
        return sorted(
            [a for a in self._actions if a.type == 'disk'],
            key=lambda x: x.label)

    def all_raids(self):
        return [a for a in self._actions if a.type == 'raid']

    def all_volgroups(self):
        return [a for a in self._actions if a.type == 'lvm_volgroup']

    def add_partition(self, disk, size, flag="", wipe=None):
        if size > disk.free_for_partitions:
            raise Exception("%s > %s", size, disk.free_for_partitions)
        real_size = align_up(size)
        log.debug("add_partition: rounded size from %s to %s", size, real_size)
        if disk._fs is not None:
            raise Exception("%s is already formatted" % (disk.label,))
        p = Partition(
            m=self, device=disk, size=real_size, flag=flag, wipe=wipe)
        if flag in ("boot", "bios_grub", "prep"):
            disk._partitions.insert(0, disk._partitions.pop())
        disk.ptable = 'gpt'
        self._actions.append(p)
        return p

    def remove_partition(self, part):
        if part._fs or part._constructed_device:
            raise Exception("can only remove empty partition")
        _remove_backlinks(part)
        self._actions.remove(part)
        if len(part.device._partitions) == 0:
            part.device.ptable = None

    def add_raid(self, name, raidlevel, devices, spare_devices):
        r = Raid(
            m=self,
            name=name,
            raidlevel=raidlevel,
            devices=devices,
            spare_devices=spare_devices)
        self._actions.append(r)
        return r

    def remove_raid(self, raid):
        if raid._fs or raid._constructed_device or len(raid.partitions()):
            raise Exception("can only remove empty RAID")
        _remove_backlinks(raid)
        self._actions.remove(raid)

    def add_volgroup(self, name, devices):
        vg = LVM_VolGroup(m=self, name=name, devices=devices)
        self._actions.append(vg)
        return vg

    def remove_volgroup(self, vg):
        if len(vg._partitions):
            raise Exception("can only remove empty VG")
        _remove_backlinks(vg)
        self._actions.remove(vg)

    def add_logical_volume(self, vg, name, size):
        lv = LVM_LogicalVolume(m=self, volgroup=vg, name=name, size=size)
        self._actions.append(lv)
        return lv

    def remove_logical_volume(self, lv):
        if lv._fs:
            raise Exception("can only remove empty LV")
        _remove_backlinks(lv)
        self._actions.remove(lv)

    def add_dm_crypt(self, volume, key):
        if not volume.available:
            raise Exception("{} is not available".format(volume))
        dm_crypt = DM_Crypt(volume=volume, key=key)
        self._actions.append(dm_crypt)
        return dm_crypt

    def remove_dm_crypt(self, dm_crypt):
        _remove_backlinks(dm_crypt)
        self._actions.remove(dm_crypt)

    def add_filesystem(self, volume, fstype):
        log.debug("adding %s to %s", fstype, volume)
        if not volume.available:
            if not isinstance(volume, Partition):
                if (volume.flag == 'prep' or (
                        volume.flag == 'bios_grub' and fstype == 'fat32')):
                    raise Exception("{} is not available".format(volume))
        if volume._fs is not None:
            raise Exception("%s is already formatted")
        fs = Filesystem(m=self, volume=volume, fstype=fstype)
        self._actions.append(fs)
        return fs

    def remove_filesystem(self, fs):
        if fs._mount:
            raise Exception("can only remove unmounted filesystem")
        _remove_backlinks(fs)
        self._actions.remove(fs)

    def add_mount(self, fs, path):
        if fs._mount is not None:
            raise Exception("%s is already mounted")
        m = Mount(m=self, device=fs, path=path)
        self._actions.append(m)
        return m

    def remove_mount(self, mount):
        _remove_backlinks(mount)
        self._actions.remove(mount)

    def needs_bootloader_partition(self):
        '''true if no disk have a boot partition, and one is needed'''
        # s390x has no such thing
        if self.bootloader == Bootloader.NONE:
            return False
        elif self.bootloader in [Bootloader.BIOS, Bootloader.PREP]:
            return self.grub_install_device is None
        elif self.bootloader == Bootloader.UEFI:
            return self._mount_for_path('/boot/efi') is None
        else:
            raise AssertionError(
                "unknown bootloader type {}".format(self.bootloader))

    def _mount_for_path(self, path):
        for mount in self.all_mounts():
            if mount.path == path:
                return mount
        return None

    def is_root_mounted(self):
        return self._mount_for_path('/') is not None

    def is_slash_boot_on_local_disk(self):
        for path in '/boot', '/':
            mount = self._mount_for_path(path)
            if mount is not None:
                dev = mount.device.volume
                return (
                    isinstance(dev, Partition)
                    and isinstance(dev.device, Disk))
        return False

    def can_install(self):
        return (self.is_root_mounted()
                and not self.needs_bootloader_partition()
                and self.is_slash_boot_on_local_disk())

    def _should_add_swapfile(self):
        mount = self._mount_for_path('/')
        if mount is not None and mount.device.fstype == 'btrfs':
            return False
        for fs in self.all_filesystems():
            if fs.fstype == "swap":
                return False
        return True
