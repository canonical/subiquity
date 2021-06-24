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
import fnmatch
import itertools
import logging
import math
import os
import pathlib
import platform
import tempfile

from curtin import storage_config
from curtin.block import partition_kname
from curtin.util import human2bytes

from probert.storage import StorageInfo

from subiquity.common.types import Bootloader


log = logging.getLogger('subiquity.models.filesystem')


def _set_backlinks(obj):
    if obj.id is None:
        base = obj.type
        i = 0
        while True:
            val = "%s-%s" % (base, i)
            if val not in obj._m._all_ids:
                break
            i += 1
        obj.id = val
    obj._m._all_ids.add(obj.id)
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
        c.id = attr.ib(default=None)
        c._m = attr.ib(repr=None, default=None)
        c = attr.s(cmp=False, repr=False)(c)
        c.__repr__ = fsobj__repr
        _type_to_cls[typ] = c
        return c
    return wrapper


def dependencies(obj):
    if obj.type == 'disk':
        dasd = obj.dasd()
        if dasd:
            yield dasd
    for f in attr.fields(type(obj)):
        v = getattr(obj, f.name)
        if not v:
            continue
        elif f.metadata.get('ref', False):
            yield v
        elif f.metadata.get('reflist', False):
            yield from v


def reverse_dependencies(obj):
    if obj.type == 'dasd':
        disk = obj._m._one(type='disk', device_id=obj.device_id)
        if disk:
            yield disk
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
    # for translators: this is a description of a RAID level
    RaidLevel(_("0 (striped)"),  "raid0",  2, False),
    # for translators: this is a description of a RAID level
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
        # Attempting to convert input to a size
        raise ValueError(_("input cannot be empty"))

    if not size[-1].isdigit():
        suffix = size[-1].upper()
        size = size[:-1]
    else:
        suffix = None

    parts = size.split('.')
    if len(parts) > 2:
        raise ValueError(
            # Attempting to convert input to a size
            _("{input!r} is not valid input").format(input=size_in))
    elif len(parts) == 2:
        div = 10 ** len(parts[1])
        size = parts[0] + parts[1]
    else:
        div = 1

    try:
        num = int(size)
    except ValueError:
        raise ValueError(
            # Attempting to convert input to a size
            _("{input!r} is not valid input").format(input=size_in))

    if suffix is not None:
        if suffix not in HUMAN_UNITS:
            raise ValueError(
                # Attempting to convert input to a size
                "unrecognized suffix {suffix!r} in {input!r}".format(
                    suffix=size_in[-1], input=size_in))
        mult = 2 ** (10 * HUMAN_UNITS.index(suffix))
    else:
        mult = 1

    if num < 0:
        # Attempting to convert input to a size
        raise ValueError("{input!r}: cannot be negative".format(input=size_in))

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


@attr.s(cmp=False)
class _Formattable(ABC):
    # Base class for anything that can be formatted and mounted,
    # e.g. a disk or a RAID or a partition.

    # Filesystem
    _fs = attributes.backlink()
    # Raid or LVM_VolGroup for now, but one day ZPool, BCache...
    _constructed_device = attributes.backlink()

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
        return any(p.available() for p in self._partitions)

    def has_unavailable_partition(self):
        return any(not p.available() for p in self._partitions)

    def _has_preexisting_partition(self):
        return any(p.preserve for p in self._partitions)


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

    def ptable_for_new_partition(self):
        if self.ptable is not None:
            return self.ptable
        dasd_config = self._m._probe_data.get('dasd', {}).get(self.path)
        if dasd_config is not None:
            if dasd_config['type'] == "FBA":
                return 'msdos'
            else:
                return 'vtoc'
        return 'gpt'

    @property
    def size(self):
        return align_down(self._info.size)

    def dasd(self):
        return self._m._one(type='dasd', device_id=self.device_id)

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
    name = attr.ib(default=None)
    multipath = attr.ib(default=None)

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

    def _path(self):
        return partition_kname(self.device.path, self._number)

    @property
    def ok_for_raid(self):
        from subiquity.common.filesystem import boot
        if boot.is_bootloader_partition(self):
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
    wipe = attr.ib(default=None)
    ptable = attributes.ptable()
    metadata = attr.ib(default=None)

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

    ok_for_raid = False
    ok_for_lvm_vg = False

    # What is a device that makes up this device referred to as?
    component_name = "PV"


@fsobj("lvm_partition")
class LVM_LogicalVolume(_Formattable):
    name = attr.ib()
    volgroup = attributes.ref(backlink="_partitions")  # LVM_VolGroup
    size = attributes.size()
    wipe = attr.ib(default=None)

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

    ok_for_raid = False
    ok_for_lvm_vg = False


LUKS_OVERHEAD = 16*(2**20)


@fsobj("dm_crypt")
class DM_Crypt:
    volume = attributes.ref(backlink="_constructed_device")  # _Formattable
    key = attr.ib(metadata={'redact': True}, default=None)
    keyfile = attr.ib(default=None)

    def serialize_key(self):
        if self.key and not self.keyfile:
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
    extra_options = attr.ib(default=None)

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
    fstype = attr.ib(default=None)
    options = attr.ib(default=None)
    spec = attr.ib(default=None)

    def can_delete(self):
        from subiquity.common.filesystem import boot
        # Can't delete mount of /boot/efi or swap, anything else is fine.
        if not self.path:
            # swap mount
            return False
        if not isinstance(self.device.volume, Partition):
            # Can't be /boot/efi if volume is not a partition
            return True
        if boot.is_esp(self.device.volume):
            # /boot/efi
            return False
        return True


def align_up(size, block_size=1 << 20):
    return (size + block_size - 1) & ~(block_size - 1)


def align_down(size, block_size=1 << 20):
    return size & ~(block_size - 1)


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

    def __init__(self, bootloader=None):
        if bootloader is None:
            bootloader = self._probe_bootloader()
        self.bootloader = bootloader
        self._probe_data = None
        self.reset()

    def reset(self):
        self._all_ids = set()
        if self._probe_data is not None:
            self._orig_config = storage_config.extract_storage_config(
                self._probe_data)["storage"]["config"]
            self._actions = self._actions_from_config(
                self._orig_config,
                self._probe_data['blockdev'],
                is_probe_data=True)
        else:
            self._orig_config = []
            self._actions = []
        self.swap = None
        self.grub = None

    def load_server_data(self, status):
        log.debug('load_server_data %s', status)
        self._all_ids = set()
        self._orig_config = status.orig_config
        self._probe_data = {
            'blockdev': status.blockdev,
            'dasd': status.dasd,
            }
        self._actions = self._actions_from_config(
            status.config,
            status.blockdev)

    def _make_matchers(self, match):
        matchers = []

        def _udev_val(disk, key):
            return self._probe_data['blockdev'].get(disk.path, {}).get(key, '')

        def match_serial(disk):
            return fnmatch.fnmatchcase(
               _udev_val(disk, "ID_SERIAL"), match['serial'])

        def match_model(disk):
            return fnmatch.fnmatchcase(
                _udev_val(disk, "ID_MODEL"), match['model'])

        def match_vendor(disk):
            return fnmatch.fnmatchcase(
                _udev_val(disk, "ID_VENDOR"), match['vendor'])

        def match_path(disk):
            return fnmatch.fnmatchcase(disk.path, match['path'])

        def match_ssd(disk):
            is_ssd = disk.info_for_display()['rotational'] == 'false'
            return is_ssd == match['ssd']

        if 'serial' in match:
            matchers.append(match_serial)
        if 'model' in match:
            matchers.append(match_model)
        if 'vendor' in match:
            matchers.append(match_vendor)
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
        if match.get('size') == 'smallest':
            candidates.sort(key=lambda d: d.size)
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
            ai_config, self._probe_data['blockdev'], is_probe_data=False)
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
                    if p.type == 'lvm_partition':
                        p.size = align_down(p.size, LVM_CHUNK_SIZE)
            elif isinstance(p.size, str):
                if p.size.endswith("%"):
                    percentage = int(p.size[:-1])
                    p.size = align_down(
                        parent.available_for_partitions*percentage//100)
                else:
                    p.size = dehumanize_size(p.size)

    def _actions_from_config(self, config, blockdevs, is_probe_data=False):
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
        for action in config:
            if is_probe_data and action['type'] == 'mount':
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
            if is_probe_data:
                kw['preserve'] = True
            obj = byid[action['id']] = c(m=self, **kw)
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

        if is_probe_data:
            for o in objs:
                if o.type == "partition" and o.flag == "swap":
                    if o._fs is None:
                        objs.append(Filesystem(
                            m=self, fstype="swap", volume=o, preserve=True))

        return objs

    def _render_actions(self, include_all=False):
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
            if not getattr(a, 'preserve', False) or include_all
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
        elif not self._should_add_swapfile():
            config['swap'] = {'swap': 0}
        if self.grub is not None:
            config['grub'] = self.grub
        return config

    def load_probe_data(self, probe_data):
        for devname, devdata in probe_data['blockdev'].items():
            if int(devdata['attrs']['size']) != 0:
                continue
            # An unformatted (ECKD) dasd reports a size of 0 via e.g. blockdev
            # --getsize64. So figuring out how big it is requires a bit more
            # work.
            data = probe_data.get('dasd', {}).get(devname)
            if data is None or data['type'] != 'ECKD':
                continue
            tracks_per_cylinder = data['tracks_per_cylinder']
            cylinders = data['cylinders']
            blocksize = 4096  # hard coded for us!
            blocks_per_track = 12  # just a mystery fact that has to be known
            size = \
                blocksize * blocks_per_track * tracks_per_cylinder * cylinders
            log.debug(
                "computing size on unformatted dasd from %s as %s", data, size)
            devdata['attrs']['size'] = str(size)
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
        from subiquity.common.filesystem import labels
        disks.sort(key=labels.label)
        return compounds + disks

    def all_disks(self):
        from subiquity.common.filesystem import labels
        return sorted(self._all(type='disk'), key=labels.label)

    def all_raids(self):
        return self._all(type='raid')

    def all_volgroups(self):
        return self._all(type='lvm_volgroup')

    def _remove(self, obj):
        _remove_backlinks(obj)
        self._actions.remove(obj)

    def add_partition(self, device, size, flag="", wipe=None,
                      grub_device=None):
        from subiquity.common.filesystem import boot
        if size > device.free_for_partitions:
            raise Exception("%s > %s", size, device.free_for_partitions)
        real_size = align_up(size)
        log.debug("add_partition: rounded size from %s to %s", size, real_size)
        if device._fs is not None:
            raise Exception("%s is already formatted" % (device,))
        p = Partition(
            m=self, device=device, size=real_size, flag=flag, wipe=wipe,
            grub_device=grub_device)
        if boot.is_bootloader_partition(p):
            device._partitions.insert(0, device._partitions.pop())
        device.ptable = device.ptable_for_new_partition()
        dasd = device.dasd()
        if dasd is not None:
            dasd.disk_layout = 'cdl'
            dasd.blocksize = 4096
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
        dm_crypt = DM_Crypt(m=self, volume=volume, key=key)
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
            raise Exception("%s is already formatted", volume)
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
            raise Exception("%s is already mounted", fs)
        m = Mount(m=self, device=fs, path=path)
        self._actions.append(m)
        return m

    def remove_mount(self, mount):
        self._remove(mount)

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
