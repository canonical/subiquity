# Copyright 2024 Canonical, Ltd.
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

"""This module defines types that are used in the storage API between the
client and server processes. View code should only use these types!"""

import enum
from typing import Any, Dict, List, Optional, Union

import attr

from subiquity.common.types import ErrorReportRef


class ProbeStatus(enum.Enum):
    PROBING = enum.auto()
    FAILED = enum.auto()
    DONE = enum.auto()


class Bootloader(enum.Enum):
    NONE = "NONE"  # a system where the bootloader is external, e.g. s390x
    BIOS = "BIOS"  # BIOS, where the bootloader dd-ed to the start of a device
    UEFI = "UEFI"  # UEFI, ESPs and /boot/efi and all that (amd64 and arm64)
    PREP = "PREP"  # ppc64el, which puts grub on a PReP partition


@attr.s(auto_attribs=True)
class OsProber:
    long: str
    label: str
    type: str
    subpath: Optional[str] = None
    version: Optional[str] = None


@attr.s(auto_attribs=True)
class Partition:
    size: Optional[int] = None
    number: Optional[int] = None
    preserve: Optional[bool] = None
    wipe: Optional[str] = None
    annotations: List[str] = attr.ib(default=attr.Factory(list))
    mount: Optional[str] = None
    format: Optional[str] = None
    # curtin's definition of partition.grub_device - in a UEFI environment,
    # this is expected to be the ESP partition mounted at /boot/efi.
    grub_device: Optional[bool] = None
    # does this partition represent the actual boot partition for this device?
    boot: Optional[bool] = None
    os: Optional[OsProber] = None
    offset: Optional[int] = None
    estimated_min_size: Optional[int] = -1
    resize: Optional[bool] = None
    path: Optional[str] = None
    # Be careful, this corresponds to the partition_name field (not the name
    # field) in the associated fsobject
    name: Optional[str] = None
    # Was this partition mounted when the installer started?
    is_in_use: bool = False
    # read-only views of mount, format, and encryption status.  Used to
    # simplify display of complex constructed objects - maybe this partition
    # isn't mounted directly but contains other devices which eventually have
    # information that we want to show.
    effective_mount: Optional[str] = None
    effective_format: Optional[str] = None
    effectively_encrypted: Optional[bool] = None


@attr.s(auto_attribs=True)
class ZFS:
    volume: str
    properties: Optional[dict] = None


@attr.s(auto_attribs=True)
class ZPool:
    pool: str
    mountpoint: str
    zfses: Optional[ZFS] = None
    pool_properties: Optional[dict] = None
    fs_properties: Optional[dict] = None
    default_features: Optional[bool] = True


class GapUsable(enum.Enum):
    YES = enum.auto()
    TOO_MANY_PRIMARY_PARTS = enum.auto()


@attr.s(auto_attribs=True)
class Gap:
    offset: int
    size: int
    usable: GapUsable


@attr.s(auto_attribs=True)
class Disk:
    id: str
    label: str
    type: str
    size: int
    usage_labels: List[str]
    partitions: List[Union[Partition, Gap]]
    ok_for_guided: bool
    ptable: Optional[str]
    preserve: bool
    path: Optional[str]
    boot_device: bool
    can_be_boot_device: bool
    model: Optional[str] = None
    vendor: Optional[str] = None
    has_in_use_partition: bool = False
    # Going forward, we want the v2 storage responses to return a list of
    # operations (e.g., reformat, add-partition, delete-partition ...) that can
    # be performed on a given disk. But we don't have this implemented yet.
    # The requires_reformat field is essentially a way to tell clients that
    # only the "reformat" operation is currently possible. No partition can be
    # added, deleted or otherwise modified on this disk until a reformat is
    # performed.
    requires_reformat: Optional[bool] = None


class GuidedCapability(enum.Enum):
    # The order listed here is the order they will be presented as options

    MANUAL = enum.auto()
    DIRECT = enum.auto()
    LVM = enum.auto()
    LVM_LUKS = enum.auto()
    ZFS = enum.auto()
    ZFS_LUKS_KEYSTORE = enum.auto()

    CORE_BOOT_ENCRYPTED = enum.auto()
    CORE_BOOT_UNENCRYPTED = enum.auto()
    # These two are not valid as GuidedChoiceV2.capability:
    CORE_BOOT_PREFER_ENCRYPTED = enum.auto()
    CORE_BOOT_PREFER_UNENCRYPTED = enum.auto()

    DD = enum.auto()

    def __lt__(self, other) -> bool:
        return self.value < other.value

    def is_lvm(self) -> bool:
        return self in [GuidedCapability.LVM, GuidedCapability.LVM_LUKS]

    def is_core_boot(self) -> bool:
        return self in [
            GuidedCapability.CORE_BOOT_ENCRYPTED,
            GuidedCapability.CORE_BOOT_UNENCRYPTED,
            GuidedCapability.CORE_BOOT_PREFER_ENCRYPTED,
            GuidedCapability.CORE_BOOT_PREFER_UNENCRYPTED,
        ]

    def supports_manual_customization(self) -> bool:
        # After posting this capability to guided_POST, is it possible
        # for the user to customize the layout further?
        return self in [
            GuidedCapability.MANUAL,
            GuidedCapability.DIRECT,
            GuidedCapability.LVM,
            GuidedCapability.LVM_LUKS,
        ]

    def is_zfs(self) -> bool:
        return self in [
            GuidedCapability.ZFS,
            GuidedCapability.ZFS_LUKS_KEYSTORE,
        ]

    def is_tpm_backed(self) -> bool:
        return self in [
            GuidedCapability.CORE_BOOT_ENCRYPTED,
            GuidedCapability.CORE_BOOT_PREFER_ENCRYPTED,
        ]

    def supports_passphrase(self) -> bool:
        return self in [
            GuidedCapability.LVM_LUKS,
            GuidedCapability.CORE_BOOT_ENCRYPTED,
            GuidedCapability.CORE_BOOT_PREFER_ENCRYPTED,
            GuidedCapability.ZFS_LUKS_KEYSTORE,
        ]

    def supports_pin(self) -> bool:
        return self in [
            GuidedCapability.CORE_BOOT_ENCRYPTED,
            GuidedCapability.CORE_BOOT_PREFER_ENCRYPTED,
        ]


class GuidedDisallowedCapabilityReason(enum.Enum):
    TOO_SMALL = enum.auto()
    CORE_BOOT_ENCRYPTION_UNAVAILABLE = enum.auto()
    NOT_UEFI = enum.auto()
    THIRD_PARTY_DRIVERS = enum.auto()


@attr.s(auto_attribs=True)
class GuidedDisallowedCapability:
    capability: GuidedCapability
    reason: GuidedDisallowedCapabilityReason
    message: Optional[str] = None


@attr.s(auto_attribs=True)
class StorageResponse:
    status: ProbeStatus
    error_report: Optional[ErrorReportRef] = None
    bootloader: Optional[Bootloader] = None
    orig_config: Optional[list] = None
    config: Optional[list] = None
    dasd: Optional[dict] = None
    storage_version: int = 1


@attr.s(auto_attribs=True)
class StorageResponseV2:
    status: ProbeStatus
    error_report: Optional[ErrorReportRef] = None
    disks: List[Disk] = attr.Factory(list)
    # if need_root == True, there is not yet a partition mounted at "/"
    need_root: Optional[bool] = None
    # if need_boot == True, there is not yet a boot partition
    need_boot: Optional[bool] = None
    install_minimum_size: Optional[int] = None


class SizingPolicy(enum.Enum):
    SCALED = enum.auto()
    ALL = enum.auto()

    @classmethod
    def from_string(cls, value):
        if value is None or value == "scaled":
            return cls.SCALED
        if value == "all":
            return cls.ALL
        raise Exception(f"Unknown SizingPolicy value {value}")


@attr.s(auto_attribs=True)
class GuidedResizeValues:
    install_max: int
    minimum: int
    recommended: int
    maximum: int


@attr.s(auto_attribs=True)
class GuidedStorageTargetReformat:
    disk_id: str
    # ptable=None means to use the default (GPT in most scenarios)
    ptable: Optional[str] = None
    allowed: List[GuidedCapability] = attr.Factory(list)
    disallowed: List[GuidedDisallowedCapability] = attr.Factory(list)


@attr.s(auto_attribs=True)
class GuidedStorageTargetResize:
    disk_id: str
    partition_number: int
    new_size: int
    minimum: Optional[int]
    recommended: Optional[int]
    maximum: Optional[int]
    allowed: List[GuidedCapability] = attr.Factory(list)
    disallowed: List[GuidedDisallowedCapability] = attr.Factory(list)

    @staticmethod
    def from_recommendations(part, resize_vals, allowed):
        return GuidedStorageTargetResize(
            disk_id=part.device.id,
            partition_number=part.number,
            new_size=resize_vals.recommended,
            minimum=resize_vals.minimum,
            recommended=resize_vals.recommended,
            maximum=resize_vals.maximum,
            allowed=allowed,
        )


@attr.s(auto_attribs=True)
class GuidedStorageTargetEraseInstall:
    disk_id: str
    partition_number: int
    allowed: List[GuidedCapability] = attr.Factory(list)
    disallowed: List[GuidedDisallowedCapability] = attr.Factory(list)


@attr.s(auto_attribs=True)
class GuidedStorageTargetUseGap:
    disk_id: str
    gap: Gap
    allowed: List[GuidedCapability] = attr.Factory(list)
    disallowed: List[GuidedDisallowedCapability] = attr.Factory(list)


@attr.s(auto_attribs=True)
class GuidedStorageTargetManual:
    allowed: List[GuidedCapability] = attr.Factory(lambda: [GuidedCapability.MANUAL])
    disallowed: List[GuidedDisallowedCapability] = attr.Factory(list)


GuidedStorageTarget = Union[
    GuidedStorageTargetEraseInstall,
    GuidedStorageTargetReformat,
    GuidedStorageTargetResize,
    GuidedStorageTargetUseGap,
    GuidedStorageTargetManual,
]


@attr.s(auto_attribs=True)
class RecoveryKey:
    # Where to store the key in the live system.
    live_location: Optional[str] = None
    # Where to copy the key in the target system. /target will automatically be
    # prefixed.
    backup_location: Optional[str] = None

    @classmethod
    def from_autoinstall(
        cls, config: Union[bool, Dict[str, Any]]
    ) -> Optional["RecoveryKey"]:
        if config is False:
            return None

        # Recovery key with default values
        if config is True:
            return cls()

        return cls(
            backup_location=config.get("backup-location"),
            live_location=config.get("live-location"),
        )


@attr.s(auto_attribs=True)
class GuidedChoiceV2:
    target: GuidedStorageTarget
    capability: GuidedCapability

    # password is used in the LUKS encryption cases, and also with TPMFDE in
    # the PASSPHRASE authentication_mode.
    password: Optional[str] = attr.ib(default=None, repr=False)
    # pin is only used with TPMFDE in the PIN authentication_mode.
    pin: Optional[str] = attr.ib(default=None, repr=False)
    recovery_key: Optional[RecoveryKey] = None

    sizing_policy: Optional[SizingPolicy] = SizingPolicy.SCALED
    reset_partition: bool = False
    reset_partition_size: Optional[int] = None

    def validate(self):
        from subiquity.server.controllers.filesystem import validate_pin_pass

        validate_pin_pass(
            passphrase_allowed=self.capability.supports_passphrase(),
            pin_allowed=self.capability.supports_pin(),
            passphrase=self.password,
            pin=self.pin,
        )


@attr.s(auto_attribs=True)
class GuidedStorageResponseV2:
    status: ProbeStatus
    error_report: Optional[ErrorReportRef] = None
    configured: Optional[GuidedChoiceV2] = None
    targets: List[GuidedStorageTarget] = attr.Factory(list)


@attr.s(auto_attribs=True)
class AddPartitionV2:
    disk_id: str
    partition: Partition
    gap: Gap


@attr.s(auto_attribs=True)
class ModifyPartitionV2:
    disk_id: str
    partition: Partition


@attr.s(auto_attribs=True)
class ReformatDisk:
    disk_id: str
    ptable: Optional[str] = None


@attr.s(auto_attribs=True)
class CalculateEntropyRequest:
    passphrase: Optional[str] = None
    pin: Optional[str] = None


@attr.s(auto_attribs=True)
class EntropyResponse:
    success: bool

    entropy_bits: int
    min_entropy_bits: int
    optimal_entropy_bits: int

    # Set to None if success is True
    failure_reasons: Optional[List[str]] = None
