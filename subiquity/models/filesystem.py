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
import fnmatch
import itertools
import logging
import math
import os
import pathlib
import platform
import tempfile

from curtin import storage_config
from curtin.util import human2bytes

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
    r = {level.value: level for level in raidlevels}
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


DEFAULT_CHUNK = 512


# The calculation of how much of a device mdadm uses for raid is more than a
# touch ridiculous. What follows is a translation of the code at:
# https://git.kernel.org/pub/scm/utils/mdadm/mdadm.git/tree/super1.c,
# specifically choose_bm_space and the end of validate_geometry1. Note that
# that calculations are in terms of 512-byte sectors.
#
# We make some assumptions about the defaults mdadm uses but mostly that the
# default metadata version is 1.2, and other formats use less space.
#
# Note that data_offset is computed for the first disk mdadm examines and then
# used for all devices, so the order matters! (Well, if the size of the
# devices vary, which is not normal but also not something we prevent).
#
# All this is tested against reality in ./scripts/get-raid-sizes.py
def calculate_data_offset_bytes(devsize):
    # Convert to sectors to make it easier to compare this code to mdadm's (we
    # convert back at the end)
    devsize >>= 9

    devsize = align_down(devsize, DEFAULT_CHUNK)

    # conversion of choose_bm_space:
    if devsize < 64*2:
        bmspace = 0
    elif devsize - 64*2 >= 200*1024*1024*2:
        bmspace = 128*2
    elif devsize - 4*2 > 8*1024*1024*2:
        bmspace = 64*2
    else:
        bmspace = 4*2

    # From the end of validate_geometry1, assuming metadata 1.2.
    headroom = 128*1024*2
    while (headroom << 10) > devsize and headroom / 2 >= DEFAULT_CHUNK*2*2:
        headroom >>= 1

    data_offset = 12*2 + bmspace + headroom
    log.debug(
        "get_raid_size: adjusting for %s sectors of overhead", data_offset)
    data_offset = align_up(data_offset, 2*1024)

    # convert back to bytes
    return data_offset << 9


def raid_device_sort(devices):
    # Because the device order matters to mdadm, we sort consistently but
    # arbitrarily when computing the size and when rendering the config (so
    # curtin passes the devices to mdadm in the order we calculate the size
    # for)
    return sorted(devices, key=lambda d: d.id)


def get_raid_size(level, devices):
    if len(devices) == 0:
        return 0
    devices = raid_device_sort(devices)
    data_offset = calculate_data_offset_bytes(devices[0].size)
    sizes = [align_down(dev.size - data_offset) for dev in devices]
    min_size = min(sizes)
    if min_size <= 0:
        return 0
    if level == "raid0":
        return sum(sizes)
    elif level == "raid1":
        return min_size
    elif level == "raid5":
        return min_size * (len(devices) - 1)
    elif level == "raid6":
        return min_size * (len(devices) - 2)
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


def _conv_size(s):
    if isinstance(s, str):
        if '%' in s:
            return s
        return int(human2bytes(s))
    return s


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
    def reflist(*, backlink=None, default=attr.NOTHING):
        metadata = {'reflist': True}
        if backlink:
            metadata['backlink'] = backlink
        return attr.ib(metadata=metadata, default=default)

    @staticmethod
    def backlink(*, default=None):
        return attr.ib(
            init=False, default=default, metadata={'is_backlink': True})

    @staticmethod
    def const(value):
        return attr.ib(default=value)

    @staticmethod
    def size():
        return attr.ib(converter=_conv_size)

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
            r.update(m())
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
    TOGGLE_BOOT = _("Make Boot Device")


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
        return _("Cannot remove {selflabel} from pre-existing {cdtype} "
                 "{cdlabel}.").format(
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
            elif self.original_fstype() is not None:
                format_desc = _("to be reformatted as {fstype}")
            else:
                format_desc = _("to be formatted as {fstype}")
            r = [format_desc.format(fstype=fs.fstype)]
            if self._m.is_mounted_filesystem(fs.fstype):
                m = fs.mount()
                if m:
                    r.append(_("mounted at {path}").format(path=m.path))
                elif getattr(self, 'flag', None) != "boot":
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

    def original_fstype(self):
        for action in self._m._orig_config:
            if action['type'] == 'format' and action['volume'] == self.id:
                return action['fstype']
        for action in self._m._orig_config:
            if action['id'] == self.id and action.get('flag') == 'swap':
                return 'swap'
        return None

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

    def dasd(self):
        return None

    def ptable_for_new_partition(self):
        if self.ptable is not None:
            return self.ptable
        for action in self._m._orig_config:
            if action['id'] == self.id:
                if action.get('ptable') == 'vtoc':
                    return action['ptable']
        if self.dasd() is not None:
            return 'vtoc'
        return 'gpt'

    def partitions(self):
        return self._partitions

    @property
    def used(self):
        if self._is_entirely_used():
            return self.size
        r = 0
        for p in self._partitions:
            if p.flag == "extended":
                continue
            r += p.size
        return r

    @property
    def empty(self):
        return self.used == 0

    @property
    def available_for_partitions(self):
        return self.size - GPT_OVERHEAD

    @property
    def free_for_partitions(self):
        return self.available_for_partitions - self.used

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


@fsobj("dasd")
class Dasd:
    device_id = attr.ib()
    blocksize = attr.ib()
    disk_layout = attr.ib()
    label = attr.ib(default=None)
    mode = attr.ib(default=None)
    preserve = attr.ib(default=False)


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
    device_id = attr.ib(default=None)

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
            return _("multipath device")
        return _("local disk")

    @property
    def label(self):
        if self.multipath:
            return self.wwn
        return self.serial or self.path

    def dasd(self):
        return self._m._one(type='dasd', device_id=self.device_id)

    def _can_be_boot_disk(self):
        bl = self._m.bootloader
        if self._has_preexisting_partition():
            if bl == Bootloader.BIOS:
                if self.ptable == "msdos":
                    return True
                else:
                    return self._partitions[0].flag == "bios_grub"
            else:
                flag = {Bootloader.UEFI: "boot", Bootloader.PREP: "prep"}[bl]
                for p in self._partitions:
                    if p.flag == flag:
                        return True
                return False
        else:
            return True

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
            actions.append(DeviceAction.TOGGLE_BOOT)
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

    @property
    def _can_PARTITION(self):
        if self._has_preexisting_partition():
            return False
        if self.free_for_partitions <= 0:
            return False
        if self.ptable == 'vtoc' and len(self._partitions) >= 3:
            return False
        return True

    _can_FORMAT = property(
        lambda self: len(self._partitions) == 0 and
        self._constructed_device is None)
    _can_REMOVE = property(_generic_can_REMOVE)

    def _is_boot_device(self):
        bl = self._m.bootloader
        if bl == Bootloader.NONE:
            return False
        elif bl == Bootloader.BIOS:
            return self.grub_device
        elif bl in [Bootloader.PREP, Bootloader.UEFI]:
            for p in self._partitions:
                if p.grub_device:
                    return True
            return False

    @property
    def _can_TOGGLE_BOOT(self):
        if self._is_boot_device():
            for disk in self._m.all_disks():
                if disk is not self and disk._is_boot_device():
                    return True
            return False
        elif self._fs is not None or self._constructed_device is not None:
            return False
        else:
            return self._can_be_boot_disk()

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
    number = attr.ib(default=None)
    preserve = attr.ib(default=False)
    grub_device = attr.ib(default=False)

    @property
    def annotations(self):
        r = super().annotations
        if self.flag == "prep":
            r.append("PReP")
            if self.preserve:
                if self.grub_device:
                    r.append(_("configured"))
                else:
                    r.append(_("unconfigured"))
        elif self.flag == "boot":
            if self.fs() and self.fs().mount():
                r.append(_("primary ESP"))
            elif self.grub_device:
                r.append(_("backup ESP"))
            else:
                r.append(_("unused ESP"))
        elif self.flag == "bios_grub":
            if self.preserve:
                if self.device.grub_device:
                    r.append(_("configured"))
                else:
                    r.append(_("unconfigured"))
            r.append("bios_grub")
        elif self.flag == "extended":
            r.append(_("extended"))
        elif self.flag == "logical":
            r.append(_("logical"))
        return r

    def usage_labels(self):
        if self.flag == "prep" or self.flag == "bios_grub":
            return []
        return super().usage_labels()

    def desc(self):
        return _("partition of {device}").format(device=self.device.desc())

    @property
    def label(self):
        return _("partition {number} of {device}").format(
            number=self._number, device=self.device.label)

    @property
    def short_label(self):
        return _("partition {number}").format(number=self._number)

    def available(self):
        if self.flag in ['bios_grub', 'prep'] or self.grub_device:
            return False
        if self._constructed_device is not None:
            return False
        if self._fs is None:
            return True
        return self._fs._available()

    def serialize_number(self):
        return {'number': self._number}

    @property
    def _number(self):
        if self.preserve:
            return self.number
        else:
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

    def serialize_devices(self):
        # Surprisingly, the order of devices passed to mdadm --create
        # matters (see get_raid_size) so we sort devices here the same
        # way get_raid_size does.
        return {'devices': [d.id for d in raid_device_sort(self.devices)]}

    spare_devices = attributes.reflist(
        backlink="_constructed_device", default=attr.Factory(set))

    preserve = attr.ib(default=False)
    ptable = attributes.ptable()

    @property
    def size(self):
        return get_raid_size(self.raidlevel, self.devices)

    @property
    def available_for_partitions(self):
        # For some reason, the overhead on RAID devices seems to be
        # higher (may be related to alignment of underlying
        # partitions)
        return self.size - 2*GPT_OVERHEAD

    @property
    def label(self):
        return self.name

    def desc(self):
        return _("software RAID {level}").format(level=self.raidlevel[4:])

    supported_actions = [
        DeviceAction.EDIT,
        DeviceAction.PARTITION,
        DeviceAction.FORMAT,
        DeviceAction.REMOVE,
        DeviceAction.DELETE,
        DeviceAction.REFORMAT,
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
    _can_REFORMAT = Disk._can_REFORMAT
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
        # Should probably query actual size somehow for an existing VG!
        return get_lvm_size(self.devices)

    @property
    def available_for_partitions(self):
        return self.size

    @property
    def annotations(self):
        r = super().annotations
        member = next(iter(self.devices))
        if member.type == "dm_crypt":
            r.append(_("encrypted"))
        return r

    @property
    def label(self):
        return self.name

    def desc(self):
        return _("LVM volume group")

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
        return {'size': "{}B".format(self.size)}

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
        return _("LVM logical volume")

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

    def serialize_key(self):
        if self.key:
            f = tempfile.NamedTemporaryFile(
                prefix='luks-key-', mode='w', delete=False)
            f.write(self.key)
            f.close()
            return {'keyfile': f.name}
        else:
            return {}

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

    target = None

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
            self._orig_config = storage_config.extract_storage_config(
                self._probe_data)["storage"]["config"]
            self._actions = self._actions_from_config(
                self._orig_config, self._probe_data['blockdev'])
        else:
            self._orig_config = []
            self._actions = []
        self.swap = None
        self.grub = None

    def _make_matchers(self, match):
        matchers = []

        def match_serial(disk):
            if disk.serial is not None:
                return fnmatch.fnmatchcase(disk.serial, match['serial'])

        def match_model(disk):
            if disk.model is not None:
                return fnmatch.fnmatchcase(disk.model, match['model'])

        def match_path(disk):
            if disk.path is not None:
                return fnmatch.fnmatchcase(disk.path, match['path'])

        def match_ssd(disk):
            is_ssd = disk.info_for_display()['rotational'] == 'false'
            return is_ssd == match['ssd']

        if 'serial' in match:
            matchers.append(match_serial)
        if 'model' in match:
            matchers.append(match_model)
        if 'path' in match:
            matchers.append(match_path)
        if 'ssd' in match:
            matchers.append(match_ssd)

        return matchers

    def disk_for_match(self, disks, match):
        matchers = self._make_matchers(match)
        candidates = []
        for candidate in disks:
            for matcher in matchers:
                if not matcher(candidate):
                    break
            else:
                candidates.append(candidate)
        if match.get('size') == 'largest':
            candidates.sort(key=lambda d: d.size, reverse=True)
        if candidates:
            return candidates[0]
        return None

    def apply_autoinstall_config(self, ai_config):
        disks = self.all_disks()
        for action in ai_config:
            if action['type'] == 'disk':
                disk = None
                if 'serial' in action:
                    disk = self._one(type='disk', serial=action['serial'])
                elif 'path' in action:
                    disk = self._one(type='disk', path=action['path'])
                else:
                    match = action.pop('match', {})
                    disk = self.disk_for_match(disks, match)
                    if disk is None:
                        action['match'] = match
                if disk is None:
                    raise Exception("{} matched no disk".format(action))
                if disk not in disks:
                    raise Exception(
                        "{} matched {} which was already used".format(
                            action, disk))
                disks.remove(disk)
                action['path'] = disk.path
                action['serial'] = disk.serial
        self._actions = self._actions_from_config(
            ai_config, self._probe_data['blockdev'], is_autoinstall=True)
        for p in self._all(type="partition") + self._all(type="lvm_partition"):
            [parent] = list(dependencies(p))
            if isinstance(p.size, int):
                if p.size < 0:
                    if p is not parent.partitions()[-1]:
                        raise Exception(
                            "{} has negative size but is not final partition "
                            "of {}".format(p, parent))
                    p.size = 0
                    p.size = parent.free_for_partitions
            elif isinstance(p.size, str):
                if p.size.endswith("%"):
                    percentage = int(p.size[:-1])
                    p.size = align_down(
                        parent.available_for_partitions*percentage//100)
                else:
                    p.size = dehumanize_size(p.size)

    def _actions_from_config(self, config, blockdevs, is_autoinstall=False):
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
            if not is_autoinstall and action['type'] == 'mount':
                if not action['path'].startswith(self.target):
                    # Completely ignore mounts under /target, they are
                    # probably leftovers from a previous install
                    # attempt.
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
            if not is_autoinstall:
                kw['preserve'] = True
            obj = byid[action['id']] = c(m=self, **kw)
            multipath = kw.get('multipath')
            if multipath:
                if multipath in seen_multipaths:
                    exclusions.add(obj)
                else:
                    seen_multipaths.add(multipath)
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

        if not is_autoinstall:
            for o in objs:
                if o.type == "partition" and o.flag == "swap":
                    if o._fs is None:
                        objs.append(Filesystem(
                            m=self, fstype="swap", volume=o, preserve=True))

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
            if isinstance(obj, Raid):
                log.debug(
                    "FilesystemModel: estimated size of %s %s is %s",
                    obj.raidlevel, obj.name, obj.size)
            r.append(asdict(obj))
            emitted_ids.add(obj.id)

        def ensure_partitions(dev):
            for part in dev.partitions():
                if part.id not in emitted_ids:
                    if part not in work and part not in next_work:
                        next_work.append(part)

        def can_emit(obj):
            if obj.type == "partition":
                ensure_partitions(obj.device)
                for p in obj.device.partitions():
                    if p._number < obj._number and p.id not in emitted_ids:
                        return False
            for dep in dependencies(obj):
                if dep.id not in emitted_ids:
                    if dep not in work and dep not in next_work:
                        next_work.append(dep)
                        if dep.type in ['disk', 'raid']:
                            ensure_partitions(dep)
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

        work = [
            a for a in self._actions
            if not getattr(a, 'preserve', False)
            ]

        while work:
            next_work = []
            for obj in work:
                if can_emit(obj):
                    emit(obj)
                else:
                    next_work.append(obj)
            if {a.id for a in next_work} == {a.id for a in work}:
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
        if self.swap is not None:
            config['swap'] = self.swap
        if self.grub is not None:
            config['grub'] = self.grub
        return config

    def load_probe_data(self, probe_data):
        self._probe_data = probe_data
        self.reset()

    def _matcher(self, type, kw):
        for a in self._actions:
            if a.type != type:
                continue
            for k, v in kw.items():
                if getattr(a, k) != v:
                    break
            else:
                yield a

    def _one(self, *, type, **kw):
        try:
            return next(self._matcher(type, kw))
        except StopIteration:
            return None

    def _all(self, *, type, **kw):
        return list(self._matcher(type, kw))

    def all_mounts(self):
        return self._all(type='mount')

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

    def all_disks(self):
        return sorted(self._all(type='disk'), key=lambda x: x.label)

    def all_raids(self):
        return self._all(type='raid')

    def all_volgroups(self):
        return self._all(type='lvm_volgroup')

    def _remove(self, obj):
        _remove_backlinks(obj)
        self._actions.remove(obj)

    def add_partition(self, device, size, flag="", wipe=None,
                      grub_device=None):
        if size > device.free_for_partitions:
            raise Exception("%s > %s", size, device.free_for_partitions)
        real_size = align_up(size)
        log.debug("add_partition: rounded size from %s to %s", size, real_size)
        if device._fs is not None:
            raise Exception("%s is already formatted" % (device.label,))
        p = Partition(
            m=self, device=device, size=real_size, flag=flag, wipe=wipe,
            grub_device=grub_device)
        if flag in ("boot", "bios_grub", "prep"):
            device._partitions.insert(0, device._partitions.pop())
        device.ptable = device.ptable_for_new_partition()
        dasd = device.dasd()
        if dasd is not None:
            dasd.device_layout = 'cdl'
            dasd.preserve = False
        self._actions.append(p)
        return p

    def remove_partition(self, part):
        if part._fs or part._constructed_device:
            raise Exception("can only remove empty partition")
        self._remove(part)
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
        self._remove(raid)

    def add_volgroup(self, name, devices):
        vg = LVM_VolGroup(m=self, name=name, devices=devices)
        self._actions.append(vg)
        return vg

    def remove_volgroup(self, vg):
        if len(vg._partitions):
            raise Exception("can only remove empty VG")
        self._remove(vg)

    def add_logical_volume(self, vg, name, size):
        lv = LVM_LogicalVolume(m=self, volgroup=vg, name=name, size=size)
        self._actions.append(lv)
        return lv

    def remove_logical_volume(self, lv):
        if lv._fs:
            raise Exception("can only remove empty LV")
        self._remove(lv)

    def add_dm_crypt(self, volume, key):
        if not volume.available:
            raise Exception("{} is not available".format(volume))
        dm_crypt = DM_Crypt(volume=volume, key=key)
        self._actions.append(dm_crypt)
        return dm_crypt

    def remove_dm_crypt(self, dm_crypt):
        self._remove(dm_crypt)

    def add_filesystem(self, volume, fstype, preserve=False):
        log.debug("adding %s to %s", fstype, volume)
        if not volume.available:
            if not isinstance(volume, Partition):
                if (volume.flag == 'prep' or (
                        volume.flag == 'bios_grub' and fstype == 'fat32')):
                    raise Exception("{} is not available".format(volume))
        if volume._fs is not None:
            raise Exception("%s is already formatted")
        fs = Filesystem(
            m=self, volume=volume, fstype=fstype, preserve=preserve)
        self._actions.append(fs)
        return fs

    def remove_filesystem(self, fs):
        if fs._mount:
            raise Exception("can only remove unmounted filesystem")
        self._remove(fs)

    def add_mount(self, fs, path):
        if fs._mount is not None:
            raise Exception("%s is already mounted")
        m = Mount(m=self, device=fs, path=path)
        self._actions.append(m)
        # Adding a swap partition or mounting btrfs at / suppresses
        # the swapfile.
        if not self._should_add_swapfile():
            self.swap = {'swap': 0}
        return m

    def remove_mount(self, mount):
        self._remove(mount)
        # Removing a mount might make it ok to add a swapfile again.
        if self._should_add_swapfile():
            self.swap = None

    def needs_bootloader_partition(self):
        '''true if no disk have a boot partition, and one is needed'''
        # s390x has no such thing
        if self.bootloader == Bootloader.NONE:
            return False
        elif self.bootloader == Bootloader.BIOS:
            return self._one(type='disk', grub_device=True) is None
        elif self.bootloader == Bootloader.UEFI:
            for esp in self._all(type='partition', grub_device=True):
                if esp.fs() and esp.fs().mount():
                    if esp.fs().mount().path == '/boot/efi':
                        return False
            return True
        elif self.bootloader == Bootloader.PREP:
            return self._one(type='partition', grub_device=True) is None
        else:
            raise AssertionError(
                "unknown bootloader type {}".format(self.bootloader))

    def _mount_for_path(self, path):
        return self._one(type='mount', path=path)

    def is_root_mounted(self):
        return self._mount_for_path('/') is not None

    def can_install(self):
        return (self.is_root_mounted()
                and not self.needs_bootloader_partition())

    def _should_add_swapfile(self):
        mount = self._mount_for_path('/')
        if mount is not None and mount.device.fstype == 'btrfs':
            return False
        for swap in self._all(type='format', fstype='swap'):
            if swap.mount():
                return False
        return True
