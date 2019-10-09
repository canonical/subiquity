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
import itertools
import logging
import math
import os
import pathlib
import platform

from curtin.util import human2bytes
from curtin import storage_config

from probert.storage import StorageInfo

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


_type_to_cls = {}


def fsobj__repr(obj):
    args = []
    for f in attr.fields(type(obj)):
        if f.name.startswith("_"):
            continue
        v = getattr(obj, f.name)
        if v is f.default:
            continue
        if f.metadata.get('ref', False):
            v = v.id
        elif f.metadata.get('reflist', False):
            if isinstance(v, set):
                delims = "{}"
            else:
                delims = "[]"
            v = delims[0] + ", ".join(vv.id for vv in v) + delims[1]
        elif f.metadata.get('redact', False):
            v = "<REDACTED>"
        else:
            v = repr(v)
        args.append("{}={}".format(f.name, v))
    return "{}({})".format(type(obj).__name__, ", ".join(args))


def fsobj(typ):
    def wrapper(c):
        c.__attrs_post_init__ = _set_backlinks
        c.type = attributes.const(typ)
        c.id = attributes.idfield(typ)
        c._m = attr.ib(repr=None, default=None)
        c = attr.s(cmp=False, repr=False)(c)
        c.__repr__ = fsobj__repr
        _type_to_cls[typ] = c
        return c
    return wrapper


def dependencies(obj):
    for f in attr.fields(type(obj)):
        v = getattr(obj, f.name)
        if not v:
            continue
        elif f.metadata.get('ref', False):
            yield v
        elif f.metadata.get('reflist', False):
            yield from v


def reverse_dependencies(obj):
    for f in attr.fields(type(obj)):
        if not f.metadata.get('is_backlink', False):
            continue
        v = getattr(obj, f.name)
        if isinstance(v, (list, set)):
            yield from v
        elif v is not None:
            yield v


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


def _raidlevels_by_value():
    r = {l.value: l for l in raidlevels}
    for n in 0, 1, 5, 6, 10:
        r[str(n)] = r[n] = r["raid"+str(n)]
    r["stripe"] = r["raid0"]
    r["mirror"] = r["raid1"]
    return r


raidlevels_by_value = _raidlevels_by_value()

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


class attributes:
    # Just a namespace to hang our wrappers around attr.ib() off.

    @staticmethod
    def idfield(base):
        i = 0

        def factory():
            nonlocal i
            r = "%s-%s" % (base, i)
            i += 1
            return r
        return attr.ib(default=attr.Factory(factory))

    @staticmethod
    def ref(*, backlink=None):
        metadata = {'ref': True}
        if backlink:
            metadata['backlink'] = backlink
        return attr.ib(metadata=metadata)

    @staticmethod
    def reflist(*, backlink=None):
        metadata = {'reflist': True}
        if backlink:
            metadata['backlink'] = backlink
        return attr.ib(metadata=metadata)

    @staticmethod
    def backlink(*, default=None):
        return attr.ib(
            init=False, default=default, metadata={'is_backlink': True})

    @staticmethod
    def const(value):
        return attr.ib(default=value)

    @staticmethod
    def size():
        return attr.ib(converter=human2bytes)

    @staticmethod
    def ptable():

        def conv(val):
            if val == "dos":
                val = "msdos"
            return val
        return attr.ib(default=None, converter=conv)


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
    REFORMAT = _("Reformat")
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
    if cd.preserve:
        return _("Cannot remove selflabel from pre-exsting {cdtype} "
                 "{cdlabel}").format(
                    selflabel=obj.label,
                    cdtype=cd.desc(),
                    cdlabel=cd.label)
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
        preserve = getattr(self, 'preserve', None)
        if preserve is None:
            return []
        elif preserve:
            return [_("existing")]
        else:
            return [_("new")]

    # Filesystem
    _fs = attributes.backlink()
    _original_fs = attributes.backlink()
    # Raid or LVM_VolGroup for now, but one day ZPool, BCache...
    _constructed_device = attributes.backlink()

    def usage_labels(self):
        cd = self.constructed_device()
        if cd is not None:
            return [
                _("{component_name} of {desc} {name}").format(
                    component_name=cd.component_name,
                    desc=cd.desc(),
                    name=cd.name),
                ]
        fs = self.fs()
        if fs is not None:
            if fs.preserve:
                format_desc = _("already formatted as {fstype}")
            elif self.original_fs() is not None:
                format_desc = _("to be reformatted as {fstype}")
            else:
                format_desc = _("to be formatted as {fstype}")
            r = [format_desc.format(fstype=fs.fstype)]
            if self._m.is_mounted_filesystem(fs.fstype):
                m = fs.mount()
                if m:
                    r.append(_("mounted at {path}").format(path=m.path))
                else:
                    r.append(_("not mounted"))
            elif fs.preserve:
                if fs.mount() is None:
                    r.append(_("unused"))
                else:
                    r.append(_("used"))
            return r
        else:
            return [_("unused")]

    def _is_entirely_used(self):
        return self._fs is not None or self._constructed_device is not None

    def fs(self):
        return self._fs

    def original_fs(self):
        return self._original_fs

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
    _partitions = attributes.backlink(default=attr.Factory(list))

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
            if not self._has_preexisting_partition():
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

    def _has_preexisting_partition(self):
        for p in self._partitions:
            if p.preserve:
                return True
        else:
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


@fsobj("disk")
class Disk(_Device):
    ptable = attributes.ptable()
    serial = attr.ib(default=None)
    wwn = attr.ib(default=None)
    multipath = attr.ib(default=None)
    path = attr.ib(default=None)
    model = attr.ib(default=None)
    wipe = attr.ib(default=None)
    preserve = attr.ib(default=False)
    name = attr.ib(default="")
    grub_device = attr.ib(default=False)

    _info = attr.ib(default=None)

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
            'model': self.model or 'unknown',
            'serial': self.serial or 'unknown',
            'wwn': self.wwn or 'unknown',
            'multipath': self.multipath or 'unknown',
            'size': self.size,
            'humansize': humanize_size(self.size),
            'vendor': self._info.vendor or 'unknown',
            'rotational': 'true' if rotational == '1' else 'false',
        }
        return dinfo

    @property
    def size(self):
        return align_down(self._info.size)

    @property
    def annotations(self):
        return []

    def desc(self):
        if self.multipath:
            return "multipath device"
        return _("local disk")

    @property
    def label(self):
        return self.wwn or self.serial or self.path

    def _potential_boot_partition(self):
        if self._m.bootloader == Bootloader.NONE:
            return None
        if not self._partitions:
            return None
        if self._m.bootloader == Bootloader.BIOS:
            if self._partitions[0].flag == "bios_grub":
                return self._partitions[0]
            else:
                return None
        flag = {
            Bootloader.UEFI: "boot",
            Bootloader.PREP: "prep",
            }[self._m.bootloader]
        for p in self._partitions:
            # XXX should check not extended in the UEFI case too (until we fix
            # that bug)
            if p.flag == flag:
                return p
        return None

    def _can_be_boot_disk(self):
        if self._m.bootloader == Bootloader.BIOS and self.ptable == "msdos":
            return True
        else:
            return self._potential_boot_partition() is not None

    @property
    def supported_actions(self):
        actions = [
            DeviceAction.INFO,
            DeviceAction.REFORMAT,
            DeviceAction.PARTITION,
            DeviceAction.FORMAT,
            DeviceAction.REMOVE,
            ]
        if self._m.bootloader != Bootloader.NONE:
            actions.append(DeviceAction.MAKE_BOOT)
        return actions

    _can_INFO = True

    @property
    def _can_REFORMAT(self):
        if len(self._partitions) == 0:
            return False
        for p in self._partitions:
            if p._constructed_device is not None:
                return False
        return True

    _can_PARTITION = property(
        lambda self: not self._has_preexisting_partition() and
        self.free_for_partitions > 0)
    _can_FORMAT = property(
        lambda self: len(self._partitions) == 0 and
        self._constructed_device is None)
    _can_REMOVE = property(_generic_can_REMOVE)

    @property
    def _can_MAKE_BOOT(self):
        bl = self._m.bootloader
        if bl == Bootloader.BIOS:
            if self._m.grub_install_device is self:
                return False
        elif bl == Bootloader.UEFI:
            m = self._m._mount_for_path('/boot/efi')
            if m and m.device.volume.device is self:
                return False
        elif bl == Bootloader.PREP:
            install_dev = self._m.grub_install_device
            if install_dev is not None and install_dev.device is self:
                return False
        if self._has_preexisting_partition():
            return self._can_be_boot_disk()
        else:
            return self._fs is None and self._constructed_device is None

    @property
    def ok_for_raid(self):
        if self._fs is not None:
            if self._fs.preserve:
                return self._fs._mount is None
            return False
        if self._constructed_device is not None:
            return False
        if len(self._partitions) > 0:
            return False
        return True

    ok_for_lvm_vg = ok_for_raid


@fsobj("partition")
class Partition(_Formattable):
    device = attributes.ref(backlink="_partitions")  # Disk
    size = attributes.size()

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

    def usage_labels(self):
        if self.flag == "prep" or self.flag == "bios_grub":
            return []
        return super().usage_labels()

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
        if self.device._has_preexisting_partition():
            return _("Cannot delete a single partition from a device that "
                     "already has partitions.")
        if self.flag in ('boot', 'bios_grub', 'prep'):
            return _("Cannot delete required bootloader partition")
        return _generic_can_DELETE(self)

    @property
    def ok_for_raid(self):
        if self.flag in ('boot', 'bios_grub', 'prep'):
            return False
        if self._fs is not None:
            if self._fs.preserve:
                return self._fs._mount is None
            return False
        if self._constructed_device is not None:
            return False
        return True

    ok_for_lvm_vg = ok_for_raid


@fsobj("raid")
class Raid(_Device):
    name = attr.ib()
    raidlevel = attr.ib(converter=lambda x: raidlevels_by_value[x].value)
    devices = attributes.reflist(backlink="_constructed_device")
    spare_devices = attributes.reflist(backlink="_constructed_device")

    preserve = attr.ib(default=False)
    ptable = attributes.ptable()

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
        if self.preserve:
            return _("Cannot edit pre-existing RAIDs.")
        elif len(self._partitions) > 0:
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
            if self._fs.preserve:
                return self._fs._mount is None
            return False
        if self._constructed_device is not None:
            return False
        if len(self._partitions) > 0:
            return False
        return True

    ok_for_lvm_vg = ok_for_raid

    # What is a device that makes up this device referred to as?
    component_name = "component"


@fsobj("lvm_volgroup")
class LVM_VolGroup(_Device):
    name = attr.ib()
    devices = attributes.reflist(backlink="_constructed_device")

    preserve = attr.ib(default=False)

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
        if self.preserve:
            return _("Cannot edit pre-existing volume groups.")
        elif len(self._partitions) > 0:
            return _(
                "Cannot edit {selflabel} because it has logical "
                "volumes.").format(
                    selflabel=self.label)
        else:
            return _generic_can_EDIT(self)

    _can_CREATE_LV = property(
        lambda self: not self.preserve and self.free_for_partitions > 0)

    ok_for_raid = False
    ok_for_lvm_vg = False

    # What is a device that makes up this device referred to as?
    component_name = "PV"


@fsobj("lvm_partition")
class LVM_LogicalVolume(_Formattable):
    name = attr.ib()
    volgroup = attributes.ref(backlink="_partitions")  # LVM_VolGroup
    size = attributes.size()

    preserve = attr.ib(default=False)

    def serialize_size(self):
        return "{}B".format(self.size)

    def available(self):
        if self._constructed_device is not None:
            return False
        if self._fs is None:
            return True
        return self._fs._available()

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

    @property
    def _can_DELETE(self):
        if self.volgroup._has_preexisting_partition():
            return _("Cannot delete a single logical volume from a volume "
                     "group that already has logical volumes.")
        return True

    ok_for_raid = False
    ok_for_lvm_vg = False


LUKS_OVERHEAD = 16*(2**20)


@fsobj("dm_crypt")
class DM_Crypt:
    volume = attributes.ref(backlink="_constructed_device")  # _Formattable
    key = attr.ib(metadata={'redact': True})

    dm_name = attr.ib(default=None)
    preserve = attr.ib(default=False)

    _constructed_device = attributes.backlink()

    def constructed_device(self):
        return self._constructed_device

    @property
    def size(self):
        return self.volume.size - LUKS_OVERHEAD


@fsobj("format")
class Filesystem:
    fstype = attr.ib()
    volume = attributes.ref(backlink="_fs")  # _Formattable

    label = attr.ib(default=None)
    uuid = attr.ib(default=None)
    preserve = attr.ib(default=False)

    _mount = attributes.backlink()

    def mount(self):
        return self._mount

    def _available(self):
        # False if mounted or if fs does not require a mount, True otherwise.
        if self._mount is None:
            if self.preserve:
                return True
            else:
                return FilesystemModel.is_mounted_filesystem(self.fstype)
        else:
            return False


@fsobj("mount")
class Mount:
    device = attributes.ref(backlink="_mount")  # Filesystem
    path = attr.ib()

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
        self._probe_data = None
        self.reset()

    def reset(self):
        if self._probe_data is not None:
            config = storage_config.extract_storage_config(self._probe_data)
            self._actions = self._actions_from_config(
                config["storage"]["config"],
                self._probe_data['blockdev'])
        else:
            self._actions = []
        self.grub_install_device = None

    def _actions_from_config(self, config, blockdevs):
        """Convert curtin storage config into action instances.

        curtin represents storage "actions" as defined in
        https://curtin.readthedocs.io/en/latest/topics/storage.html.  We
        convert each action (that we know about) into an instance of
        Disk, Partition, RAID, etc (unknown actions, e.g. bcache, are
        just ignored).

        We also filter out anything that can be reached from a currently
        mounted device. The motivation here is only to exclude the media
        subiquity is mounted from, so this might be a bit excessive but
        hey it works.

        Perhaps surprisingly the order of the returned actions matters.
        The devices are presented in the filesystem view in the reverse
        of the order they appear in _actions, which means that e.g. a
        RAID appears higher up the list than the disks is is composed
        of. This is quite important as it makes "unpeeling" existing
        compound structures easy, you just delete the top device until
        you only have disks left.
        """
        byid = {}
        objs = []
        exclusions = set()
        seen_multipaths = set()
        for action in config:
            if action['type'] == 'mount':
                exclusions.add(byid[action['device']])
                continue
            c = _type_to_cls.get(action['type'], None)
            if c is None:
                # Ignore any action we do not know how to process yet
                # (e.g. bcache)
                continue
            kw = {}
            for f in attr.fields(c):
                n = f.name
                if n not in action:
                    continue
                v = action[n]
                try:
                    if f.metadata.get('ref', False):
                        kw[n] = byid[v]
                    elif f.metadata.get('reflist', False):
                        kw[n] = [byid[id] for id in v]
                    else:
                        kw[n] = v
                except KeyError:
                    # If a dependency of the current action has been
                    # ignored, we need to ignore the current action too
                    # (e.g. a bcache's filesystem).
                    continue
            if kw['type'] == 'disk':
                path = kw['path']
                kw['info'] = StorageInfo({path: blockdevs[path]})
            kw['preserve'] = True
            obj = byid[action['id']] = c(m=self, **kw)
            multipath = kw.get('multipath')
            if multipath:
                if multipath in seen_multipaths:
                    exclusions.add(obj)
                else:
                    seen_multipaths.add(multipath)
            if action['type'] == "format":
                obj.volume._original_fs = obj
            objs.append(obj)

        while True:
            next_exclusions = exclusions.copy()
            for e in exclusions:
                next_exclusions.update(itertools.chain(
                    dependencies(e), reverse_dependencies(e)))
            if len(exclusions) == len(next_exclusions):
                break
            exclusions = next_exclusions

        log.debug("exclusions %s", {e.id for e in exclusions})

        objs = [o for o in objs if o not in exclusions]

        for o in objs:
            if o.type == "partition" and o.flag == "swap" and o._fs is None:
                fs = Filesystem(m=self, fstype="swap", volume=o, preserve=True)
                o._original_fs = fs
                objs.append(fs)

        return objs

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
                msg = ["rendering block devices made no progress processing:"]
                for w in work:
                    msg.append(" - " + str(w))
                raise Exception("\n".join(msg))
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

    def load_probe_data(self, probe_data):
        self._probe_data = probe_data
        self.reset()

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

    def re_add_filesystem(self, fs):
        _set_backlinks(fs)
        self._actions.append(fs)

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

    def can_install(self):
        return (self.is_root_mounted()
                and not self.needs_bootloader_partition())

    def _should_add_swapfile(self):
        mount = self._mount_for_path('/')
        if mount is not None and mount.device.fstype == 'btrfs':
            return False
        for fs in self.all_filesystems():
            if fs.fstype == "swap":
                return False
        return True
