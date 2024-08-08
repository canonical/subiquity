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

import collections
import copy
import enum
import fnmatch
import logging
import math
import os
import pathlib
import platform
import secrets
import tempfile
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple, Union

import attr
import more_itertools
from curtin import storage_config
from curtin.block import partition_kname
from curtin.swap import can_use_swapfile
from curtin.util import human2bytes
from probert.storage import StorageInfo

from subiquity.common.types.storage import (
    Bootloader,
    OsProber,
    RecoveryKey,
    StorageResponse,
)
from subiquity.server.autoinstall import AutoinstallError
from subiquitycore.utils import write_named_tempfile

log = logging.getLogger("subiquity.models.filesystem")

MiB = 1024 * 1024
GiB = 1024 * 1024 * 1024


class NotFinalPartitionError(Exception):
    """Exception to raise when guessing the size of a partition that is not
    the last one."""


@attr.s(auto_attribs=True)
class RecoveryKeyHandler:
    # Where to store the key on the live system
    live_location: Optional[pathlib.Path]
    # Where to store the key in the target system. /target will automatically
    # be prefixed.
    backup_location: pathlib.Path

    _key: Optional[str] = attr.ib(repr=False, default=None)

    @classmethod
    def from_post_data(
        cls, data: Optional[RecoveryKey], default_suffix="recovery-key.txt"
    ) -> Optional["RecoveryKeyHandler"]:
        """Create RecoveryKeyHandler instance from POST-ed RecoveryKey data."""
        if data is None:
            return None

        # Set default values for unspecified settings.
        live_location = pathlib.Path("~").expanduser() / default_suffix
        backup_location = pathlib.Path("/var/log/installer") / default_suffix

        if data.live_location is not None:
            live_location = pathlib.Path(data.live_location)
        if data.backup_location is not None:
            backup_location = pathlib.Path(data.backup_location)

        return cls(live_location=live_location, backup_location=backup_location)

    def load_key_from_file(self, location: pathlib.Path) -> None:
        """Load the key from the file specified"""
        with location.open(mode="r", encoding="utf-8") as fh:
            self._key = fh.read().strip()

    def generate(self):
        """Generate a key and store internally"""
        self._key = FilesystemModel.generate_recovery_key()

    def _expose_key(
        self,
        location: pathlib.Path,
        root: pathlib.Path,
        parents_perm: int,
        key_perm: int,
    ) -> None:
        full_location = root / location.relative_to(location.root)

        if not full_location.resolve().is_relative_to(root):
            raise RuntimeError(
                "Trying to copy recovery key outside of" " designated root directory"
            )

        full_location.parent.mkdir(mode=parents_perm, parents=True, exist_ok=True)

        with full_location.open(mode="w", encoding="utf-8") as fh:
            fh.write(self._key)
        full_location.chmod(key_perm)

    def expose_key_to_live_system(self, root: Optional[pathlib.Path] = None) -> None:
        """Write the key to the live system - so it can be retrieved by the
        user of the installer."""
        if root is None:
            root = pathlib.Path("/")

        self._expose_key(
            location=self.live_location, root=root, parents_perm=0o755, key_perm=0o644
        )

    def copy_key_to_target_system(self, target: pathlib.Path) -> None:
        """Write the key to the target system - so it can be retrieved after
        the install by an admin."""

        self._expose_key(
            location=self.backup_location,
            root=target,
            parents_perm=0o700,
            key_perm=0o600,
        )


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
        backlink = field.metadata.get("backlink")
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
        backlink = field.metadata.get("backlink")
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
        if f.metadata.get("ref", False):
            v = v.id
        elif f.metadata.get("reflist", False):
            if isinstance(v, set):
                delims = "{}"
            else:
                delims = "[]"
            v = delims[0] + ", ".join(vv.id for vv in v) + delims[1]
        elif f.metadata.get("redact", False):
            v = "<REDACTED>"
        else:
            v = repr(v)
        args.append("{}={}".format(f.name, v))
    return "{}({})".format(type(obj).__name__, ", ".join(args))


def _do_post_inits(obj):
    for fn in obj._post_inits:
        fn(obj)


def fsobj(typ):
    def wrapper(c):
        c.__attrs_post_init__ = _do_post_inits
        c._post_inits = [_set_backlinks]
        class_post_init = getattr(c, "__post_init__", None)
        if class_post_init is not None:
            c._post_inits.append(class_post_init)
        c.type = attributes.const(typ)
        c.id = attr.ib(default=None)
        c._m = attr.ib(repr=None, default=None)
        c.__annotations__["id"] = str
        c.__annotations__["_m"] = "FilesystemModel"
        c.__annotations__["type"] = str
        c = attr.s(eq=False, repr=False, auto_attribs=True, kw_only=True)(c)
        c.__repr__ = fsobj__repr
        _type_to_cls[typ] = c
        return c

    return wrapper


def dependencies(obj):
    if obj.type == "disk":
        dasd = obj.dasd()
        if dasd:
            yield dasd
    for f in attr.fields(type(obj)):
        v = getattr(obj, f.name)
        if not v:
            continue
        elif f.metadata.get("ref", False):
            yield v
        elif f.metadata.get("reflist", False):
            yield from v


def reverse_dependencies(obj):
    if obj.type == "dasd":
        disk = obj._m._one(type="disk", device_id=obj.device_id)
        if disk:
            yield disk
    for f in attr.fields(type(obj)):
        if not f.metadata.get("is_backlink", False):
            continue
        v = getattr(obj, f.name)
        if isinstance(v, (list, set)):
            yield from v
        elif v is not None:
            yield v


def is_logical_partition(obj):
    try:
        return obj.is_logical
    except AttributeError:
        return False


@attr.s(eq=False)
class RaidLevel:
    name = attr.ib()
    value = attr.ib()
    min_devices = attr.ib()
    supports_spares = attr.ib(default=True)


raidlevels = [
    # for translators: this is a description of a RAID level
    RaidLevel(_("0 (striped)"), "raid0", 2, False),
    # for translators: this is a description of a RAID level
    RaidLevel(_("1 (mirrored)"), "raid1", 2),
    RaidLevel(_("5"), "raid5", 3),
    RaidLevel(_("6"), "raid6", 4),
    RaidLevel(_("10"), "raid10", 4),
    RaidLevel(_("Container"), "container", 2),
]


def _raidlevels_by_value():
    r = {level.value: level for level in raidlevels}
    for n in 0, 1, 5, 6, 10:
        r[str(n)] = r[n] = r["raid" + str(n)]
    r["stripe"] = r["raid0"]
    r["mirror"] = r["raid1"]
    return r


raidlevels_by_value = _raidlevels_by_value()

HUMAN_UNITS = ["B", "K", "M", "G", "T", "P"]


def humanize_size(size):
    if size == 0:
        return "0B"
    p = int(math.floor(math.log(size, 2) / 10))
    # We want to truncate the non-integral part, not round to nearest.
    s = "{:.17f}".format(size / 2 ** (10 * p))
    i = s.index(".")
    s = s[: i + 4]
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

    parts = size.split(".")
    if len(parts) > 2:
        raise ValueError(
            # Attempting to convert input to a size
            _("{input!r} is not valid input").format(input=size_in)
        )
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
            _("{input!r} is not valid input").format(input=size_in)
        )

    if suffix is not None:
        if suffix not in HUMAN_UNITS:
            raise ValueError(
                # Attempting to convert input to a size
                "unrecognized suffix {suffix!r} in {input!r}".format(
                    suffix=size_in[-1], input=size_in
                )
            )
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
    if devsize < 64 * 2:
        bmspace = 0
    elif devsize - 64 * 2 >= 200 * 1024 * 1024 * 2:
        bmspace = 128 * 2
    elif devsize - 4 * 2 > 8 * 1024 * 1024 * 2:
        bmspace = 64 * 2
    else:
        bmspace = 4 * 2

    # From the end of validate_geometry1, assuming metadata 1.2.
    headroom = 128 * 1024 * 2
    while (headroom << 10) > devsize and headroom / 2 >= DEFAULT_CHUNK * 2 * 2:
        headroom >>= 1

    data_offset = 12 * 2 + bmspace + headroom
    log.debug("get_raid_size: adjusting for %s sectors of overhead", data_offset)
    data_offset = align_up(data_offset, 2 * 1024)

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
    if level == "raid0" or level == "container":
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
LVM_OVERHEAD = 1 << 20
LVM_CHUNK_SIZE = 4 * (1 << 20)


def get_lvm_size(devices, size_overrides={}):
    r = 0
    for d in devices:
        r += align_down(size_overrides.get(d, d.size) - LVM_OVERHEAD, LVM_CHUNK_SIZE)
    return r


def _conv_size(s):
    if isinstance(s, str):
        if "%" in s:
            return s
        return int(human2bytes(s))
    return s


class attributes:
    # Just a namespace to hang our wrappers around attr.ib() off.

    @staticmethod
    def ref(*, backlink=None, default=attr.NOTHING):
        metadata = {"ref": True}
        if backlink:
            metadata["backlink"] = backlink
        return attr.ib(metadata=metadata, default=default)

    @staticmethod
    def reflist(*, backlink=None, default=attr.NOTHING):
        metadata = {"reflist": True}
        if backlink:
            metadata["backlink"] = backlink
        return attr.ib(metadata=metadata, default=default)

    @staticmethod
    def backlink(*, default=None):
        return attr.ib(init=False, default=default, metadata={"is_backlink": True})

    @staticmethod
    def const(value):
        return attr.ib(default=value)

    @staticmethod
    def size(default=None):
        return attr.ib(converter=_conv_size, default=None)

    @staticmethod
    def ptable():
        def conv(val):
            if val == "dos":
                val = "msdos"
            return val

        return attr.ib(default=None, converter=conv)

    @staticmethod
    def for_api(*, default=attr.NOTHING):
        return attr.ib(default=default, metadata={"for_api": True})


def asdict(inst, *, for_api: bool):
    r = collections.OrderedDict()
    for field in attr.fields(type(inst)):
        metadata = field.metadata
        if not for_api or not metadata.get("for_api", False):
            if field.name.startswith("_"):
                continue
        name = field.name.lstrip("_")
        m = getattr(inst, "serialize_" + name, None)
        if m:
            r.update(m())
        else:
            v = getattr(inst, field.name)
            if v is not None:
                if metadata.get("ref", False):
                    r[name] = v.id
                elif metadata.get("reflist", False):
                    r[name] = [elem.id for elem in v]
                elif isinstance(v, StorageInfo):
                    r[name] = {v.name: v.raw}
                else:
                    r[name] = v
    return r


# This code is not going to make much sense unless you have read
# http://curtin.readthedocs.io/en/latest/topics/storage.html. The
# Disk, Partition etc classes correspond to entries in curtin's
# storage config list. They are mostly 'dumb data', all the logic is
# in the FilesystemModel or FilesystemController classes.


@attr.s(eq=False)
class _Formattable(ABC):
    # Base class for anything that can be formatted and mounted,
    # e.g. a disk or a RAID or a partition.

    _fs: Optional["Filesystem"] = attributes.backlink()
    _constructed_device: Optional["ConstructedDevice"] = attributes.backlink()
    _is_in_use: bool = attributes.for_api(default=False)

    def _is_entirely_used(self):
        return self._fs is not None or self._constructed_device is not None

    def fs(self):
        return self._fs

    def original_fstype(self):
        for action in self._m._orig_config:
            if action["type"] == "format" and action["volume"] == self.id:
                return action["fstype"]
        for action in self._m._orig_config:
            if action["id"] == self.id and action.get("flag") == "swap":
                return "swap"
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
    def format(self):
        if not self._fs:
            return None
        return self._fs.fstype

    @property
    def mount(self) -> Optional[str]:
        if not self._fs or not self._fs._mount:
            return None
        return self._fs._mount.path

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


@attr.s(eq=False)
class _Device(_Formattable, ABC):
    # Anything that can have partitions, e.g. a disk or a RAID.

    @property
    @abstractmethod
    def size(self):
        pass

    # [Partition]
    _partitions: List["Partition"] = attributes.backlink(default=attr.Factory(list))

    def _reformatted(self):
        # Return a ephemeral copy of the device with as many partitions
        # deleted as possible.
        new_disk = attr.evolve(self)
        new_disk._partitions = [p for p in self.partitions() if p._is_in_use]
        return new_disk

    def dasd(self):
        return None

    def ptable_for_new_partition(self):
        if self.ptable is not None:
            return self.ptable
        return "gpt"

    def partitions(self):
        return self._partitions

    def partitions_by_offset(self):
        return sorted(self._partitions, key=lambda p: p.offset)

    def partitions_by_number(self):
        return sorted(self._partitions, key=lambda p: p.number)

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
        raise NotImplementedError

    def available(self):
        # A _Device is available if:
        # 1) it is not part of a device like a RAID or LVM or ZPool or ...
        # 2) if it is formatted, it is available if it is formatted with fs
        #    that needs to be mounted and is not mounted
        # 3) if it is not formatted, it is available if it has free
        #    space OR at least one partition is not formatted or is formatted
        #    with a fs that needs to be mounted and is not mounted
        if self._constructed_device is not None:
            return False
        if self._is_in_use:
            return False
        if self._fs is not None:
            return self._fs._available()
        from subiquity.common.filesystem.gaps import largest_gap_size

        if largest_gap_size(self) > 0:
            return True
        return any(p.available() for p in self._partitions)

    def has_unavailable_partition(self):
        return any(not p.available() for p in self._partitions)

    def _has_preexisting_partition(self):
        return any(p.preserve for p in self._partitions)

    def renumber_logical_partitions(self, removed_partition):
        parts = [
            p
            for p in self.partitions_by_number()
            if p.is_logical and p.number > removed_partition.number
        ]
        next_num = removed_partition.number
        for part in parts:
            part.number = next_num
            next_num += 1

    def on_remote_storage(self) -> bool:
        raise NotImplementedError


@fsobj("dasd")
class Dasd:
    device_id: str
    blocksize: int
    disk_layout: str
    label: Optional[str] = None
    mode: Optional[str] = None
    preserve: bool = False


@fsobj("nvme_controller")
class NVMeController:
    transport: str
    tcp_port: Optional[int] = None
    tcp_addr: Optional[str] = None
    preserve: bool = False


@fsobj("disk")
class Disk(_Device):
    ptable: Optional[str] = attributes.ptable()
    serial: Optional[str] = None
    wwn: Optional[str] = None
    multipath: Optional[str] = None
    nvme_controller: Optional[NVMeController] = attributes.ref(default=None)
    path: Optional[str] = None
    wipe: Optional[str] = None
    preserve: bool = False
    name: str = ""
    grub_device: bool = False
    device_id: Optional[str] = None

    _info: StorageInfo = attributes.for_api()
    _has_in_use_partition: bool = attributes.for_api(default=False)

    @property
    def available_for_partitions(self):
        margin_before = self.alignment_data().min_start_offset
        margin_after = self.alignment_data().min_end_offset
        return align_down(self.size, 1 << 20) - margin_before - margin_after

    def alignment_data(self):
        ptable = self.ptable_for_new_partition()
        return self._m._partition_alignment_data[ptable]

    def info_for_display(self):
        bus = self._info.raw.get("ID_BUS", None)
        major = self._info.raw.get("MAJOR", None)
        if bus is None and major == "253":
            bus = "virtio"

        devpath = self._info.raw.get("DEVPATH", self.path)
        # XXX probert should be doing this!!
        rotational = "1"
        try:
            dev = os.path.basename(devpath)
            rfile = "/sys/class/block/{}/queue/rotational".format(dev)
            with open(rfile, "r") as f:
                rotational = f.read().strip()
        except (PermissionError, FileNotFoundError, IOError):
            log.exception("WARNING: Failed to read file {}".format(rfile))

        dinfo = {
            "bus": bus,
            "devname": self.path,
            "devpath": devpath,
            "model": self.model or "unknown",
            "serial": self.serial or "unknown",
            "wwn": self.wwn or "unknown",
            "multipath": self.multipath or "unknown",
            "nvme-controller": self.nvme_controller,
            "size": self.size,
            "humansize": humanize_size(self.size),
            "vendor": self._info.vendor or "unknown",
            "rotational": "true" if rotational == "1" else "false",
        }
        return dinfo

    def ptable_for_new_partition(self):
        if self.ptable is not None:
            return self.ptable
        dasd_config = self._m._probe_data.get("dasd", {}).get(self.path)
        if dasd_config is not None:
            if dasd_config["type"] == "FBA":
                return "msdos"
            else:
                return "vtoc"
        return "gpt"

    @property
    def size(self):
        return self._info.size

    def dasd(self):
        return self._m._one(type="dasd", device_id=self.device_id)

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
        if self.on_remote_storage():
            return False
        return True

    @property
    def ok_for_lvm_vg(self):
        return self.ok_for_raid and self.size > LVM_OVERHEAD

    @property
    def model(self):
        return self._decode_id("ID_MODEL_ENC")

    @property
    def vendor(self):
        return self._decode_id("ID_VENDOR_ENC")

    def _decode_id(self, id):
        id = self._info.raw.get(id)
        if id is None:
            return None
        return id.encode("utf-8").decode("unicode_escape").strip()

    def on_remote_storage(self) -> bool:
        if self.nvme_controller and self.nvme_controller.transport == "tcp":
            return True
        return False


@fsobj("partition")
class Partition(_Formattable):
    device: _Device = attributes.ref(backlink="_partitions")
    size: int = attributes.size()

    wipe: Optional[str] = None
    flag: Optional[str] = None
    number: Optional[int] = None
    preserve: bool = False
    grub_device: bool = False
    name: Optional[str] = None
    multipath: Optional[str] = None
    offset: Optional[int] = None
    resize: Optional[bool] = None
    partition_type: Optional[str] = None
    partition_name: Optional[str] = None
    path: Optional[str] = None
    uuid: Optional[str] = None

    _info: Optional[StorageInfo] = attributes.for_api(default=None)

    def __post_init__(self):
        if self.number is not None:
            return

        used_nums = {
            p.number
            for p in self.device._partitions
            if p.number is not None
            if p.is_logical == self.is_logical
        }
        primary_limit = self.device.alignment_data().primary_part_limit
        if self.is_logical:
            possible_nums = range(primary_limit + 1, 129)
        else:
            possible_nums = range(1, primary_limit + 1)
        for num in possible_nums:
            if num not in used_nums:
                self.number = num
                return
        raise Exception("Exceeded number of available partitions")

    def available(self):
        if self.flag in ["bios_grub", "prep"] or self.grub_device:
            return False
        if self._is_in_use:
            return False
        if self._constructed_device is not None:
            return False
        if self._fs is None:
            return True
        return self._fs._available()

    def _path(self):
        return partition_kname(self.device.path, self.number)

    @property
    def boot(self):
        from subiquity.common.filesystem import boot

        return boot.is_bootloader_partition(self)

    @property
    def estimated_min_size(self):
        fs_data = self._m._probe_data.get("filesystem", {}).get(self._path())
        if fs_data is None:
            return -1
        val = fs_data.get("ESTIMATED_MIN_SIZE", -1)
        if val == 0:
            return self.device.alignment_data().part_align
        if val == -1:
            return -1
        return align_up(val, self.device.alignment_data().part_align)

    @property
    def ok_for_raid(self):
        if self.boot:
            return False
        if self._fs is not None:
            if self._fs.preserve:
                return self._fs._mount is None
            return False
        if self._constructed_device is not None:
            return False
        if self.on_remote_storage():
            return False
        return True

    @property
    def ok_for_lvm_vg(self):
        return self.ok_for_raid and self.size > LVM_OVERHEAD

    @property
    def os(self):
        os_data = self._m._probe_data.get("os", {}).get(self._path())
        if not os_data:
            return None
        return OsProber(**os_data)

    @property
    def is_logical(self):
        if self.flag == "logical":
            return True

        if self.number is None:
            # Should only be possible during initialization.
            return False

        # There is not guarantee that a logical partition will have its flag
        # set to 'logical'. For a swap partition, for instance, the partition's
        # flag will be set to 'swap'.  For MSDOS partitions tables, we need to
        # check the partition number.
        return self.device.ptable == "msdos" and self.number > 4

    def on_remote_storage(self) -> bool:
        return self.device.on_remote_storage()


@fsobj("raid")
class Raid(_Device):
    name: str
    raidlevel: str = attr.ib(converter=lambda x: raidlevels_by_value[x].value)
    devices: Set[Union[Disk, Partition, "Raid"]] = attributes.reflist(
        backlink="_constructed_device", default=attr.Factory(set)
    )
    _info: Optional[StorageInfo] = attributes.for_api(default=None)
    _has_in_use_partition = False

    def serialize_devices(self):
        # Surprisingly, the order of devices passed to mdadm --create
        # matters (see get_raid_size) so we sort devices here the same
        # way get_raid_size does.
        return {"devices": [d.id for d in raid_device_sort(self.devices)]}

    spare_devices: Set[Union[Disk, Partition, "Raid"]] = attributes.reflist(
        backlink="_constructed_device", default=attr.Factory(set)
    )

    preserve: bool = False
    wipe: Optional[str] = None
    ptable: Optional[str] = attributes.ptable()
    metadata: Optional[str] = None
    _path: Optional[str] = None
    container: Optional["Raid"] = attributes.ref(backlink="_subvolumes", default=None)
    _subvolumes: List["Raid"] = attributes.backlink(default=attr.Factory(list))

    @property
    def path(self):
        if self._path is not None:
            return self._path
        # This is just here to make for_client(raid-with-partitions) work. It
        # might not be very accurate.
        return "/dev/md/" + self.name

    @path.setter
    def path(self, value):
        self._path = value

    @property
    def size(self):
        if self.preserve:
            return self._info.size
        return get_raid_size(self.raidlevel, self.devices)

    def alignment_data(self):
        ptable = self.ptable_for_new_partition()
        return self._m._partition_alignment_data[ptable]

    @property
    def available_for_partitions(self):
        # For some reason, the overhead on RAID devices seems to be
        # higher (may be related to alignment of underlying
        # partitions)
        return self.size - 2 * GPT_OVERHEAD

    def available(self):
        if self.raidlevel == "container":
            return False
        return super().available()

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
        if self.raidlevel == "container":
            return False
        return True

    @property
    def ok_for_lvm_vg(self):
        return self.ok_for_raid and self.size > LVM_OVERHEAD

    # What is a device that makes up this device referred to as?
    component_name = "component"

    def on_remote_storage(self) -> bool:
        for dev in self.devices:
            if dev.on_remote_storage():
                return True

        return False


@fsobj("lvm_volgroup")
class LVM_VolGroup(_Device):
    name: str
    devices: List[Union[Disk, Partition, Raid]] = attributes.reflist(
        backlink="_constructed_device"
    )

    preserve: bool = False

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

    def on_remote_storage(self) -> bool:
        for dev in self.devices:
            if dev.on_remote_storage():
                return True
        return False


@fsobj("lvm_partition")
class LVM_LogicalVolume(_Formattable):
    name: str
    volgroup: LVM_VolGroup = attributes.ref(backlink="_partitions")
    size: int = attributes.size(default=None)
    wipe: Optional[str] = None

    preserve: bool = False
    path: Optional[str] = None

    def serialize_size(self):
        if self.size is None:
            return {}
        else:
            return {"size": "{}B".format(self.size)}

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

    def on_remote_storage(self) -> bool:
        return self.volgroup.on_remote_storage()


LUKS_OVERHEAD = 16 * (2**20)


@fsobj("dm_crypt")
class DM_Crypt(_Formattable):
    volume: _Formattable = attributes.ref(backlink="_constructed_device")
    key: Optional[str] = attr.ib(metadata={"redact": True}, default=None)
    keyfile: Optional[str] = None
    options: Optional[List[str]] = None
    recovery_key: Optional[RecoveryKeyHandler] = None
    _recovery_keyfile: Optional[str] = None
    _recovery_live_location: Optional[str] = None
    _recovery_backup_location: Optional[str] = None
    path: Optional[str] = None

    def __post_init__(self) -> None:
        # When the object is created using _actions_from_config, we should
        # build the recovery_key object.
        if self._recovery_keyfile is None or self.recovery_key is not None:
            return

        props: Dict[str, pathlib.Path] = {}
        if self._recovery_live_location:
            props["live_location"] = pathlib.Path(self._recovery_live_location)
        if self._recovery_backup_location:
            props["backup_location"] = pathlib.Path(self._recovery_backup_location)
        self.recovery_key = RecoveryKeyHandler(**props)

    def serialize_key(self):
        if self.key and not self.keyfile:
            return {"keyfile": write_named_tempfile("luks-key-", self.key)}
        else:
            return {}

    def serialize_recovery_key(self) -> str:
        if self.recovery_key is None:
            return {"recovery_keyfile": None}

        # A bit of a hack to make sure the recovery key gets created when
        # converting the DM_Crypt object to a dict.
        if self._recovery_keyfile is None:
            self.assign_recovery_key()

        props = {"recovery_keyfile": self._recovery_keyfile}

        if self.recovery_key.live_location is not None:
            props["recovery_live_location"] = str(self.recovery_key.live_location)
        if self.recovery_key.backup_location is not None:
            props["recovery_backup_location"] = str(self.recovery_key.backup_location)

        return props

    def assign_recovery_key(self):
        """Create the recovery key and temporary store it in a keyfile."""
        f = tempfile.NamedTemporaryFile(
            prefix="luks-recovery-key-", mode="w", delete=False
        )
        if self.recovery_key._key is None:
            self.recovery_key.generate()

        f.write(self.recovery_key._key)
        f.close()
        self._recovery_keyfile = f.name

    dm_name: Optional[str] = None
    preserve: bool = False

    _constructed_device: Optional["ConstructedDevice"] = attributes.backlink()

    def constructed_device(self):
        return self._constructed_device

    @property
    def size(self):
        return self.volume.size - LUKS_OVERHEAD

    def available(self):
        if self._is_in_use:
            return False
        if self._constructed_device is not None:
            return False
        if self._fs is None:
            return True
        return self._fs._available()

    @property
    def ok_for_raid(self):
        if self._fs is not None:
            if self._fs.preserve:
                return self._fs._mount is None
            return False
        if self._constructed_device is not None:
            return False
        return True

    @property
    def ok_for_lvm_vg(self):
        return self.ok_for_raid and self.size > LVM_OVERHEAD

    def on_remote_storage(self) -> bool:
        return self.volume.on_remote_storage()


@fsobj("device")
class ArbitraryDevice(_Device):
    ptable: Optional[str] = None
    path: Optional[str] = None

    @property
    def size(self):
        return 0

    ok_for_raid = False
    ok_for_lvm_vg = False


@fsobj("format")
class Filesystem:
    fstype: str
    volume: _Formattable = attributes.ref(backlink="_fs")

    label: Optional[str] = None
    uuid: Optional[str] = None
    preserve: bool = False
    extra_options: Optional[List[str]] = None

    _mount: Optional["Mount"] = attributes.backlink()

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
    path: str
    device: Filesystem = attributes.ref(backlink="_mount", default=None)
    fstype: Optional[str] = None
    options: Optional[str] = None
    spec: Optional[str] = None

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


def get_canmount(properties: Optional[dict], default: bool) -> bool:
    """Handle the possible values of the zfs canmount property, which should be
    on/off/noauto.  Due to yaml handling, on/off may be turned into a bool, so
    handle that also."""
    if properties is None:
        return default
    vals = {
        "on": True,
        "off": False,
        "noauto": False,
        True: True,
        False: False,
    }
    result = vals.get(properties.get("canmount", default))
    if result is None:
        raise ValueError('canmount must be one of "on", "off", or "noauto"')
    return result


@fsobj("zpool")
class ZPool:
    vdevs: List[Union[Disk, Partition]] = attributes.reflist(
        backlink="_constructed_device"
    )
    pool: str
    mountpoint: str

    _zfses: List["ZFS"] = attributes.backlink(default=attr.Factory(list))

    # storage options on the pool
    pool_properties: Optional[dict] = None
    # default dataset options for the zfses in the pool
    fs_properties: Optional[dict] = None

    default_features: Optional[bool] = True
    encryption_style: Optional[str] = None
    keyfile: Optional[str] = None

    component_name = "vdev"

    @property
    def fstype(self):
        return "zfs"

    @property
    def name(self):
        return self.pool

    @property
    def canmount(self):
        return get_canmount(self.fs_properties, False)

    @property
    def path(self):
        if self.canmount:
            return self.mountpoint
        return None

    def create_zfs(self, volume, canmount="on", mountpoint=None):
        properties = {}
        if canmount is not None:
            properties["canmount"] = canmount
        if mountpoint is not None:
            properties["mountpoint"] = mountpoint
        if len(properties) < 1:
            properties = None
        zfs = ZFS(m=self._m, pool=self, volume=volume, properties=properties)
        self._m._actions.append(zfs)
        return zfs


@fsobj("zfs")
class ZFS:
    pool: ZPool = attributes.ref(backlink="_zfses")
    volume: str
    # options to pass to zfs dataset creation
    properties: Optional[dict] = None

    @property
    def fstype(self):
        return "zfs"

    @property
    def canmount(self):
        return get_canmount(self.properties, False)

    @property
    def path(self):
        if self.canmount:
            return self.properties.get("mountpoint", self.volume)
        else:
            return None


ConstructedDevice = Union[Raid, LVM_VolGroup, ZPool]

# A Mountlike is a literal Mount object, or one similar enough in behavior.
# Mountlikes have a path property that may return None if that given object is
# not actually mountable.
MountlikeNames = ("mount", "zpool", "zfs")


def align_up(size, block_size=1 << 20):
    return (size + block_size - 1) & ~(block_size - 1)


def align_down(size, block_size=1 << 20):
    return size & ~(block_size - 1)


@attr.s(auto_attribs=True)
class PartitionAlignmentData:
    part_align: int
    min_gap_size: int
    min_start_offset: int
    min_end_offset: int
    primary_part_limit: int
    ebr_space: int = 0


class ActionRenderMode(enum.Enum):
    # The default for FilesystemModel.render() is to render actions
    # for devices that have changes, but not e.g. a hard drive that
    # will be untouched by the installation process.
    DEFAULT = enum.auto()
    # FOR_API means render actions for all model objects and include
    # information that is only used by client/server communication,
    # not curtin.
    FOR_API = enum.auto()
    # FOR_API_CLIENT means render actions for devices that have
    # changes and include information that is only used by
    # client/server communication, not curtin.
    FOR_API_CLIENT = enum.auto()
    # DEVICES means to just render actions for setting up block
    # devices, e.g. partitioning disks and assembling RAIDs but not
    # any format or mount actions.
    DEVICES = enum.auto()
    # FORMAT_MOUNT means to just render actions to format and mount
    # the block devices. References to block devices will be replaced
    # by "type: device" actions that just refer to the block devices
    # by path.
    FORMAT_MOUNT = enum.auto()

    def is_api(self):
        return self in [ActionRenderMode.FOR_API, ActionRenderMode.FOR_API_CLIENT]

    def include_all(self):
        return self in [ActionRenderMode.FOR_API]


class FilesystemModel:
    target = None

    _partition_alignment_data = {
        "gpt": PartitionAlignmentData(
            part_align=MiB,
            min_gap_size=MiB,
            min_start_offset=GPT_OVERHEAD // 2,
            min_end_offset=GPT_OVERHEAD // 2,
            primary_part_limit=128,
        ),
        "msdos": PartitionAlignmentData(
            part_align=MiB,
            min_gap_size=MiB,
            min_start_offset=GPT_OVERHEAD // 2,
            min_end_offset=0,
            ebr_space=MiB,
            primary_part_limit=4,
        ),
        # XXX check this one!!
        "vtoc": PartitionAlignmentData(
            part_align=MiB,
            min_gap_size=MiB,
            min_start_offset=GPT_OVERHEAD // 2,
            min_end_offset=0,
            ebr_space=MiB,
            primary_part_limit=3,
        ),
    }

    @classmethod
    def is_mounted_filesystem(self, fstype):
        if fstype in [None, "swap"]:
            return False
        else:
            return True

    def _probe_bootloader(self):
        # This will at some point change to return a list so that we can
        # configure BIOS _and_ UEFI on amd64 systems.
        if os.path.exists("/sys/firmware/efi"):
            return Bootloader.UEFI
        elif platform.machine().startswith("ppc64"):
            return Bootloader.PREP
        elif platform.machine() == "s390x":
            return Bootloader.NONE
        else:
            return Bootloader.BIOS

    def __init__(
        self,
        bootloader=None,
        *,
        root: str,
        opt_supports_nvme_tcp_booting: bool | None = None,
        detected_supports_nvme_tcp_booting: bool | None = None,
    ):
        if bootloader is None:
            bootloader = self._probe_bootloader()
        self.bootloader = bootloader
        self.root = root
        self.opt_supports_nvme_tcp_booting: bool | None = opt_supports_nvme_tcp_booting
        self.detected_supports_nvme_tcp_booting: bool | None = (
            detected_supports_nvme_tcp_booting
        )
        self.storage_version = 1
        self._probe_data = None
        self.dd_target: Optional[Disk] = None
        self.reset_partition: Optional[Partition] = None
        self.reset()

    def reset(self):
        self._all_ids = set()
        if self._probe_data is not None:
            self.process_probe_data()
        else:
            self._orig_config = []
            self._actions = []
        self.swap = None
        self.grub = None
        self.guided_configuration = None

    def get_orig_model(self):
        # The purpose of this is to be able to answer arbitrary questions about
        # the original state.  _orig_config plays a similar role, but is
        # expressed in terms of curtin actions, which are not what we want to
        # use on the V2 storage API.
        orig_model = FilesystemModel(
            self.bootloader,
            root=self.root,
            opt_supports_nvme_tcp_booting=self.opt_supports_nvme_tcp_booting,
            detected_supports_nvme_tcp_booting=self.detected_supports_nvme_tcp_booting,
        )

        orig_model.target = self.target
        if self._probe_data is not None:
            orig_model.load_probe_data(self._probe_data)
        return orig_model

    @property
    def supports_nvme_tcp_booting(self) -> bool:
        if self.opt_supports_nvme_tcp_booting is not None:
            return self.opt_supports_nvme_tcp_booting

        assert self.detected_supports_nvme_tcp_booting is not None
        return self.detected_supports_nvme_tcp_booting

    def process_probe_data(self):
        self._orig_config = storage_config.extract_storage_config(self._probe_data)[
            "storage"
        ]["config"]
        self._actions = self._actions_from_config(
            self._orig_config,
            blockdevs=self._probe_data["blockdev"],
            is_probe_data=True,
        )

        majmin_to_dev = {}

        for obj in self._actions:
            if not hasattr(obj, "_info"):
                continue
            major = obj._info.raw.get("MAJOR")
            minor = obj._info.raw.get("MINOR")
            if major is None or minor is None:
                continue
            majmin_to_dev[f"{major}:{minor}"] = obj

        log.debug("majmin_to_dev %s", majmin_to_dev)

        mounts = list(self._probe_data.get("mount", []))
        while mounts:
            mount = mounts.pop(0)
            mounts.extend(mount.get("children", []))
            if mount["target"].startswith(self.target):
                # Completely ignore mounts under /target, they are probably
                # leftovers from a previous install attempt.
                continue
            if "maj:min" not in mount:
                continue
            log.debug("considering mount of %s", mount["maj:min"])
            obj = majmin_to_dev.get(mount["maj:min"])
            if obj is None:
                continue
            obj._is_in_use = True
            log.debug("%s is mounted", obj.path)
            work = [obj]
            while work:
                o = work.pop(0)
                if isinstance(o, Disk):
                    o._has_in_use_partition = True
                work.extend(dependencies(o))

        # This is a special hack for the install media. When written to a USB
        # stick or similar, both the block device for the whole drive and for
        # the partition will show up as having a filesystem. Casper should
        # preferentially mount it as a partition though and if it looks like
        # that has happened, we ignore the filesystem on the drive itself.
        for disk in self._all(type="disk"):
            if disk._fs is None:
                continue
            if not disk._partitions:
                continue
            p1 = disk._partitions[0]
            if p1._fs is None:
                continue
            if disk._fs.fstype == p1._fs.fstype == "iso9660":
                if p1._is_in_use and not disk._is_in_use:
                    self.remove_filesystem(disk._fs)

        for o in self._actions:
            if o.type == "partition" and o.flag == "swap":
                if o._fs is None:
                    self._actions.append(
                        Filesystem(m=self, fstype="swap", volume=o, preserve=True)
                    )

    def load_server_data(self, status: StorageResponse):
        log.debug("load_server_data %s", status)
        self._all_ids = set()
        self.storage_version = status.storage_version
        self._orig_config = status.orig_config
        self._probe_data = {
            "dasd": status.dasd,
        }
        self._actions = self._actions_from_config(
            status.config, blockdevs=None, is_probe_data=False
        )

    def _make_matchers(self, match: dict) -> Sequence[Callable]:
        def _udev_val(disk, key):
            return self._probe_data["blockdev"].get(disk.path, {}).get(key, "")

        def match_serial(disk):
            return fnmatch.fnmatchcase(_udev_val(disk, "ID_SERIAL"), match["serial"])

        def match_model(disk):
            return fnmatch.fnmatchcase(_udev_val(disk, "ID_MODEL"), match["model"])

        def match_vendor(disk):
            return fnmatch.fnmatchcase(_udev_val(disk, "ID_VENDOR"), match["vendor"])

        def match_path(disk):
            return fnmatch.fnmatchcase(disk.path, match["path"])

        def match_id_path(disk):
            return fnmatch.fnmatchcase(_udev_val(disk, "ID_PATH"), match["id_path"])

        def match_devpath(disk):
            return fnmatch.fnmatchcase(_udev_val(disk, "DEVPATH"), match["devpath"])

        def match_ssd(disk):
            is_ssd = disk.info_for_display()["rotational"] == "false"
            return is_ssd == match["ssd"]

        def match_install_media(disk):
            return disk._has_in_use_partition

        def match_not_in_use(disk):
            return not disk._has_in_use_partition

        def match_nonzero_size(disk):
            return disk.size != 0

        matchers = [match_nonzero_size]

        if match.get("install-media", False):
            matchers.append(match_install_media)

        if "serial" in match:
            matchers.append(match_serial)
        if "model" in match:
            matchers.append(match_model)
        if "vendor" in match:
            matchers.append(match_vendor)
        if "path" in match:
            matchers.append(match_path)
        if "id_path" in match:
            matchers.append(match_id_path)
        if "devpath" in match:
            matchers.append(match_devpath)
        if "ssd" in match:
            matchers.append(match_ssd)
        if "size" in match or "ssd" in match:
            matchers.append(match_not_in_use)

        return matchers

    def _sorted_matches(self, disks: Sequence[_Device], match: dict):
        if match.get("size") == "smallest":
            disks.sort(key=lambda d: d.size)
        elif match.get("size") == "largest":
            disks.sort(key=lambda d: d.size, reverse=True)
        return disks

    def _filtered_matches(self, disks: Sequence[_Device], match: dict):
        matchers = self._make_matchers(match)
        return [disk for disk in disks if all(match_fn(disk) for match_fn in matchers)]

    def disk_for_match(
        self, disks: Sequence[_Device], match: dict | Sequence[dict]
    ) -> _Device:
        # a match directive is a dict, or a list of dicts, that specify
        # * zero or more keys to filter on
        # * an optional sort on size
        log.info(f"considering {disks} for {match}")
        if isinstance(match, dict):
            match = [match]
        for m in match:
            candidates = self._filtered_matches(disks, m)
            candidates = self._sorted_matches(candidates, m)
            if candidates:
                log.info(f"For match {m}, using the first candidate from {candidates}")
                return candidates[0]
        log.info(f"No devices satisfy criteria {match}")
        return None

    def assign_omitted_offsets(self):
        """Assign offsets to partitions that do not already have one.
        This method does nothing for storage version 1."""
        if self.storage_version != 2:
            return

        for disk in self._all(type="disk"):
            info = disk.alignment_data()

            def au(v):  # au == "align up"
                r = v % info.part_align
                if r:
                    return v + info.part_align - r
                else:
                    return v

            def ad(v):  # ad == "align down"
                return v - v % info.part_align

            # Extended is considered a primary partition too.
            primary_parts, logical_parts = map(
                list, more_itertools.partition(is_logical_partition, disk.partitions())
            )

            prev_end = info.min_start_offset
            for part in primary_parts:
                if part.offset is None:
                    part.offset = au(prev_end)
                prev_end = part.offset + part.size

            if not logical_parts:
                return

            extended_part = next(
                filter(lambda x: x.flag == "extended", disk.partitions())
            )

            prev_end = extended_part.offset
            for part in logical_parts:
                if part.offset is None:
                    part.offset = au(prev_end + info.ebr_space)
                prev_end = part.offset + part.size

    def apply_autoinstall_config(self, ai_config):
        disks = self.all_disks()
        for action in ai_config:
            if action["type"] == "disk":
                disk = None
                if "serial" in action:
                    disk = self._one(type="disk", serial=action["serial"])
                elif "path" in action:
                    disk = self._one(type="disk", path=action["path"])
                else:
                    match = action.pop("match", {})
                    disk = self.disk_for_match(disks, match)
                    if disk is None:
                        action["match"] = match
                if disk is None:
                    raise AutoinstallError("{} matched no disk".format(action))
                if disk not in disks:
                    raise AutoinstallError(
                        "{} matched {} which was already used".format(action, disk)
                    )
                disks.remove(disk)
                action["path"] = disk.path
                action["serial"] = disk.serial
        self._actions = self._actions_from_config(
            ai_config, blockdevs=self._probe_data["blockdev"], is_probe_data=False
        )

        self.assign_omitted_offsets()

        for p in self._all(type="partition") + self._all(type="lvm_partition"):
            # NOTE For logical partitions (DOS), the parent is set to the disk,
            # not the extended partition.
            [parent] = list(dependencies(p))
            if isinstance(p.size, int):
                if p.size < 0:
                    if p.flag == "extended":
                        # For extended partitions, we use this filter to create
                        # a temporary copy of the disk that excludes all
                        # logical partitions.
                        def filter_(x):
                            return not is_logical_partition(x)

                    else:

                        def filter_(x):
                            return True

                    filtered_parent = copy.copy(parent)
                    filtered_parent._partitions = list(
                        filter(filter_, parent.partitions())
                    )
                    if p is not filtered_parent.partitions()[-1]:
                        raise NotFinalPartitionError(
                            "{} has negative size but is not final partition "
                            "of {}".format(p, parent)
                        )

                    # Exclude the current partition itself so that its
                    # incomplete size is not used as is.
                    filtered_parent._partitions.remove(p)

                    from subiquity.common.filesystem.gaps import largest_gap_size

                    p.size = largest_gap_size(
                        filtered_parent, in_extended=is_logical_partition(p)
                    )
            elif isinstance(p.size, str):
                if p.size.endswith("%"):
                    percentage = int(p.size[:-1])
                    p.size = align_down(
                        parent.available_for_partitions * percentage // 100
                    )
                else:
                    p.size = dehumanize_size(p.size)

    def _actions_from_config(self, config, *, blockdevs, is_probe_data):
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
        for action in config:
            if is_probe_data and action["type"] == "mount":
                continue
            c = _type_to_cls.get(action["type"], None)
            if c is None:
                # Ignore any action we do not know how to process yet
                # (e.g. bcache)
                log.debug(f'ignoring unknown action type {action["type"]}')
                continue
            kw = {}
            field_names = set()
            for f in attr.fields(c):
                n = f.name.lstrip("_")
                field_names.add(f.name)
                if n not in action:
                    continue
                v = action[n]
                try:
                    if f.metadata.get("ref", False):
                        kw[n] = byid[v]
                    elif f.metadata.get("reflist", False):
                        kw[n] = [byid[id] for id in v]
                    else:
                        kw[n] = v
                except KeyError:
                    # If a dependency of the current action has been
                    # ignored, we need to ignore the current action too
                    # (e.g. a bcache's filesystem).
                    continue
            if "_info" in field_names:
                if "info" in kw:
                    kw["info"] = StorageInfo(kw["info"])
                elif "path" in kw:
                    path = kw["path"]
                    kw["info"] = StorageInfo({path: blockdevs[path]})
            if is_probe_data:
                kw["preserve"] = True
            obj = byid[action["id"]] = c(m=self, **kw)
            objs.append(obj)

        return objs

    def _render_actions(self, mode: ActionRenderMode = ActionRenderMode.DEFAULT):
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
                    obj.raidlevel,
                    obj.name,
                    obj.size,
                )
            r.append(asdict(obj, for_api=mode.is_api()))
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
                    if p.number < obj.number and p.id not in emitted_ids:
                        return False
            for dep in dependencies(obj):
                if dep.id not in emitted_ids:
                    if dep not in work and dep not in next_work:
                        next_work.append(dep)
                        if dep.type in ["disk", "raid"]:
                            ensure_partitions(dep)
                    return False
            if obj.type in MountlikeNames and obj.path is not None:
                # Any mount actions for a parent of this one have to be emitted
                # first.
                for parent in pathlib.Path(obj.path).parents:
                    parent = str(parent)
                    if parent in mountpoints:
                        if mountpoints[parent] not in emitted_ids:
                            log.debug(
                                "cannot emit action to mount %s until that "
                                "for %s is emitted",
                                obj.path,
                                parent,
                            )
                            return False
            return True

        mountpoints = {m.path: m.id for m in self.all_mountlikes()}
        log.debug("mountpoints %s", mountpoints)

        if mode.include_all():
            work = list(self._actions)
        else:
            work = [a for a in self._actions if not getattr(a, "preserve", False)]

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

        if mode == ActionRenderMode.DEVICES:
            r = [act for act in r if act["type"] not in ("format", "mount")]
        if mode == ActionRenderMode.FORMAT_MOUNT:
            r = [act for act in r if act["type"] in ("format", "mount")]
            devices = []
            for act in r:
                if act["type"] == "format":
                    device = {
                        "type": "device",
                        "id": "synth-device-{}".format(len(devices)),
                        "path": self._one(id=act["volume"]).path,
                    }
                    devices.append(device)
                    act["volume"] = device["id"]
            r = devices + r

        return r

    def render(self, mode: ActionRenderMode = ActionRenderMode.DEFAULT):
        if self.dd_target is not None:
            return {
                "partitioning_commands": {
                    "builtin": [
                        "curtin",
                        "block-meta",
                        "simple",
                        "--devices",
                        self.dd_target.path,
                    ],
                },
            }
        config = {
            "storage": {
                "version": self.storage_version,
                "config": self._render_actions(mode=mode),
            },
        }
        if self.swap is not None:
            config["swap"] = self.swap
        elif not self.should_add_swapfile():
            config["swap"] = {"size": 0}
        if self.grub is not None:
            config["grub"] = self.grub
        return config

    def load_probe_data(self, probe_data):
        for devname, devdata in probe_data["blockdev"].items():
            if int(devdata["attrs"]["size"]) != 0:
                continue
            # An unformatted (ECKD) dasd reports a size of 0 via e.g. blockdev
            # --getsize64. So figuring out how big it is requires a bit more
            # work.
            data = probe_data.get("dasd", {}).get(devname)
            if data is None or data["type"] != "ECKD":
                continue
            tracks_per_cylinder = data["tracks_per_cylinder"]
            cylinders = data["cylinders"]
            blocksize = 4096  # hard coded for us!
            blocks_per_track = 12  # just a mystery fact that has to be known
            size = blocksize * blocks_per_track * tracks_per_cylinder * cylinders
            log.debug("computing size on unformatted dasd from %s as %s", data, size)
            devdata["attrs"]["size"] = str(size)
        self._probe_data = probe_data
        self.reset()

    def _matcher(self, kw):
        for a in self._actions:
            for k, v in kw.items():
                if getattr(a, k) != v:
                    break
            else:
                yield a

    def _one(self, **kw):
        try:
            return next(self._matcher(kw))
        except StopIteration:
            return None

    def _all(self, **kw):
        return list(self._matcher(kw))

    def all_mounts(self):
        return self._all(type="mount")

    def all_mountlikes(self):
        ret = []
        for typename in MountlikeNames:
            ret += self._all(type=typename)
        return ret

    def all_devices(self):
        # return:
        #  compound devices, newest first
        #  disk devices, sorted by label
        disks = []
        compounds = []
        for a in self._actions:
            if a.type == "disk":
                disks.append(a)
            elif isinstance(a, _Device):
                compounds.append(a)
        compounds.reverse()
        from subiquity.common.filesystem import labels

        disks.sort(key=labels.label)
        return compounds + disks

    def all_disks(self):
        from subiquity.common.filesystem import labels

        return sorted(self._all(type="disk"), key=labels.label)

    def all_raids(self):
        return self._all(type="raid")

    def all_volgroups(self):
        return self._all(type="lvm_volgroup")

    def all_dm_crypts(self):
        return self._all(type="dm_crypt")

    def partition_by_partuuid(self, partuuid: str) -> Optional[Partition]:
        return self._one(type="partition", uuid=partuuid)

    def _remove(self, obj):
        _remove_backlinks(obj)
        self._actions.remove(obj)

    def add_partition(
        self,
        device,
        *,
        size,
        offset,
        flag="",
        wipe=None,
        grub_device=None,
        partition_name=None,
        check_alignment=True,
    ):
        align = device.alignment_data().part_align
        if check_alignment:
            if offset % align != 0 or size % align != 0:
                raise Exception(
                    "size %s or offset %s not aligned to %s", size, offset, align
                )
        from subiquity.common.filesystem import boot

        if device._fs is not None:
            raise Exception("%s is already formatted" % (device,))
        p = Partition(
            m=self,
            device=device,
            size=size,
            flag=flag,
            wipe=wipe,
            grub_device=grub_device,
            offset=offset,
            partition_name=partition_name,
        )
        if boot.is_bootloader_partition(p):
            device._partitions.insert(0, device._partitions.pop())
        device.ptable = device.ptable_for_new_partition()
        dasd = device.dasd()
        if dasd is not None:
            dasd.disk_layout = "cdl"
            dasd.blocksize = 4096
            dasd.preserve = False
        self._actions.append(p)
        return p

    def remove_partition(self, part):
        if part._fs or part._constructed_device:
            raise Exception("can only remove empty partition")
        from subiquity.common.filesystem.gaps import (
            movable_trailing_partitions_and_gap_size,
        )

        for p2 in movable_trailing_partitions_and_gap_size(part)[0]:
            p2.offset -= part.size
        self._remove(part)
        part.device.renumber_logical_partitions(part)
        if len(part.device._partitions) == 0:
            part.device.ptable = None

    def add_raid(self, name, raidlevel, devices, spare_devices):
        r = Raid(
            m=self,
            name=name,
            raidlevel=raidlevel,
            devices=devices,
            spare_devices=spare_devices,
        )
        self._actions.append(r)
        return r

    def remove_raid(self, raid: Raid):
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

    def add_logical_volume(self, vg: LVM_VolGroup, name: str, size: int | None):
        lv = LVM_LogicalVolume(m=self, volgroup=vg, name=name, size=size)
        self._actions.append(lv)
        return lv

    def remove_logical_volume(self, lv: LVM_LogicalVolume):
        if lv._fs:
            raise Exception("can only remove empty LV")
        self._remove(lv)

    def add_dm_crypt(
        self,
        volume,
        *,
        key: Optional[str] = None,
        keyfile: Optional[str] = None,
        options: Optional[List[str]] = None,
        recovery_key: Optional[RecoveryKeyHandler] = None,
        root: Optional[pathlib.Path] = None,
    ):
        if not volume.available:
            raise Exception("{} is not available".format(volume))

        dm_crypt = DM_Crypt(
            m=self,
            volume=volume,
            key=key,
            keyfile=keyfile,
            options=options,
            recovery_key=recovery_key,
        )
        self._actions.append(dm_crypt)
        return dm_crypt

    def remove_dm_crypt(self, dm_crypt):
        self._remove(dm_crypt)

    def add_filesystem(self, volume, fstype, preserve=False, label=None):
        log.debug("adding %s to %s", fstype, volume)
        if not volume.available:
            if not isinstance(volume, Partition):
                if volume.flag == "prep" or (
                    volume.flag == "bios_grub" and fstype == "fat32"
                ):
                    raise Exception("{} is not available".format(volume))
        if volume._fs is not None:
            raise Exception(f"{volume} is already formatted")
        fs = Filesystem(
            m=self, volume=volume, fstype=fstype, preserve=preserve, label=label
        )
        self._actions.append(fs)
        return fs

    def remove_filesystem(self, fs):
        if fs._mount:
            raise Exception("can only remove unmounted filesystem")
        self._remove(fs)

    def add_mount(self, fs, path, *, on_remote_storage=False):
        if fs._mount is not None:
            raise Exception(f"{fs} is already mounted")
        options = None
        if on_remote_storage:
            options = "defaults,_netdev"
        m = Mount(m=self, device=fs, path=path, options=options)
        self._actions.append(m)
        return m

    def remove_mount(self, mount):
        self._remove(mount)

    def needs_bootloader_partition(self):
        """true if no disk have a boot partition, and one is needed"""
        # s390x has no such thing
        if self.bootloader == Bootloader.NONE:
            return False
        elif self.bootloader == Bootloader.BIOS:
            return self._one(type="disk", grub_device=True) is None
        elif self.bootloader == Bootloader.UEFI:
            for esp in self._all(type="partition", grub_device=True):
                if esp.fs() and esp.fs().mount():
                    if esp.fs().mount().path == "/boot/efi":
                        return False
            return True
        elif self.bootloader == Bootloader.PREP:
            return self._one(type="partition", grub_device=True) is None
        else:
            raise AssertionError("unknown bootloader type {}".format(self.bootloader))

    def _mount_for_path(self, path):
        for typename in MountlikeNames:
            mount = self._one(type=typename, path=path)
            if mount is not None:
                return mount
        return None

    def is_root_mounted(self):
        return self._mount_for_path("/") is not None

    def is_rootfs_on_remote_storage(self) -> bool:
        return self._mount_for_path("/").device.volume.on_remote_storage()

    def is_boot_mounted(self) -> bool:
        return self._mount_for_path("/boot") is not None

    def is_bootfs_on_remote_storage(self) -> bool:
        return self._mount_for_path("/boot").device.volume.on_remote_storage()

    def _can_install_remote(self) -> bool:
        """Tells whether installing with the rootfs on remote storage would be
        a supported use-case with the current configuration.
        It requires either:
         * firmware support for booting with NVMe/TCP
         * the boot FS (i.e., kernel + initramfs) to be stored on local storage.
        """
        if self.supports_nvme_tcp_booting:
            return True

        return self.is_boot_mounted() and not self.is_bootfs_on_remote_storage()

    def can_install(self) -> bool:
        if not self.is_root_mounted():
            return False

        if self.is_rootfs_on_remote_storage() and not self._can_install_remote():
            return False

        if self.needs_bootloader_partition():
            return False

        return True

    def should_add_swapfile(self):
        mount = self._mount_for_path("/")
        if mount is not None:
            if not can_use_swapfile("/", mount.device.fstype):
                return False
        for swap in self._all(type="format", fstype="swap"):
            if swap.mount():
                return False
        return True

    def add_zpool(
        self,
        device,
        pool,
        mountpoint,
        *,
        default_features=True,
        fs_properties=None,
        pool_properties=None,
        encryption_style=None,
        keyfile=None,
    ):
        zpool = ZPool(
            m=self,
            vdevs=[device],
            pool=pool,
            mountpoint=mountpoint,
            default_features=default_features,
            pool_properties=pool_properties,
            fs_properties=fs_properties,
            encryption_style=encryption_style,
            keyfile=keyfile,
        )
        self._actions.append(zpool)
        return zpool

    async def live_packages(self) -> Tuple[Set, Set]:
        before = set()
        during = set()
        if self._one(type="zpool") is not None:
            before.add("zfsutils-linux")
        if self.reset_partition is not None:
            during.add("efibootmgr")
        return (before, during)

    @staticmethod
    def generate_recovery_key() -> str:
        """Return a new recovery key suitable for LUKS encryption. The key will
        consist of 48 decimal digits."""
        digits = 48
        return str(secrets.randbelow(10**digits)).zfill(digits)

    def load_or_generate_recovery_keys(self) -> None:
        for dm_crypt in self.all_dm_crypts():
            if dm_crypt.recovery_key is None:
                continue
            if dm_crypt.recovery_key._key is not None:
                continue
            if dm_crypt._recovery_keyfile is not None:
                dm_crypt.recovery_key.load_key_from_file(
                    pathlib.Path(dm_crypt._recovery_keyfile)
                )
            else:
                dm_crypt.recovery_key.generate()

    def expose_recovery_keys(self) -> None:
        for dm_crypt in self.all_dm_crypts():
            if dm_crypt.recovery_key is None:
                continue
            handler = dm_crypt.recovery_key

            if handler.live_location is None:
                continue

            handler.expose_key_to_live_system(root=self.root)

    def copy_artifacts_to_target(self) -> None:
        for dm_crypt in self.all_dm_crypts():
            if dm_crypt.recovery_key is None:
                continue

            log.debug(
                "Copying recovery key for %s to target: %s", dm_crypt, self.target
            )
            dm_crypt.recovery_key.copy_key_to_target_system(target=self.target)
