# Copyright 2020 Canonical, Ltd.
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

# This module defines types that will be used in the API when subiquity gets
# split into client and server processes.  View code should only use these
# types!

import datetime
import enum
import shlex
from typing import Any, Dict, List, Optional, Union

import attr

from subiquitycore.models.network import NetDevInfo

from subiquity.common.serialize import named_field


class ErrorReportState(enum.Enum):
    INCOMPLETE = enum.auto()
    LOADING = enum.auto()
    DONE = enum.auto()
    ERROR_GENERATING = enum.auto()
    ERROR_LOADING = enum.auto()


class ErrorReportKind(enum.Enum):
    BLOCK_PROBE_FAIL = _("Block device probe failure")
    DISK_PROBE_FAIL = _("Disk probe failure")
    INSTALL_FAIL = _("Install failure")
    UI = _("Installer crash")
    NETWORK_FAIL = _("Network error")
    NETWORK_CLIENT_FAIL = _("Network client error")
    SERVER_REQUEST_FAIL = _("Server request failure")
    UNKNOWN = _("Unknown error")


@attr.s(auto_attribs=True)
class ErrorReportRef:
    state: ErrorReportState
    base: str
    kind: ErrorReportKind
    seen: bool
    oops_id: Optional[str]


class ApplicationState(enum.Enum):
    """ Represents the state of the application at a given time. """

    # States reported during the initial stages of the installation.
    STARTING_UP = enum.auto()
    CLOUD_INIT_WAIT = enum.auto()
    EARLY_COMMANDS = enum.auto()

    # State reported once before starting destructive actions.
    NEEDS_CONFIRMATION = enum.auto()

    # States reported during installation. This sequence should be expected
    # multiple times until we reach the late stages.
    WAITING = enum.auto()
    RUNNING = enum.auto()

    # States reported while unattended-upgrades is running.
    # TODO: check if these should be dropped in favor of RUNNING.
    UU_RUNNING = enum.auto()
    UU_CANCELLING = enum.auto()

    # Final state
    DONE = enum.auto()
    ERROR = enum.auto()
    EXITED = enum.auto()


@attr.s(auto_attribs=True)
class ApplicationStatus:
    state: ApplicationState
    confirming_tty: str
    error: Optional[ErrorReportRef]
    cloud_init_ok: Optional[bool]
    interactive: Optional[bool]
    echo_syslog_id: str
    log_syslog_id: str
    event_syslog_id: str


class PasswordKind(enum.Enum):
    NONE = enum.auto()
    KNOWN = enum.auto()
    UNKNOWN = enum.auto()


@attr.s(auto_attribs=True)
class KeyFingerprint:
    keytype: str
    fingerprint: str


@attr.s(auto_attribs=True)
class LiveSessionSSHInfo:
    username: str
    password_kind: PasswordKind
    password: Optional[str]
    authorized_key_fingerprints: List[KeyFingerprint]
    ips: List[str]
    host_key_fingerprints: List[KeyFingerprint]


class RefreshCheckState(enum.Enum):
    UNKNOWN = enum.auto()
    AVAILABLE = enum.auto()
    UNAVAILABLE = enum.auto()


@attr.s(auto_attribs=True)
class RefreshStatus:
    availability: RefreshCheckState
    current_snap_version: str = ''
    new_snap_version: str = ''


@attr.s(auto_attribs=True)
class StepPressKey:
    # "Press a key with one of the following symbols"
    symbols: List[str]
    keycodes: Dict[int, str]


@attr.s(auto_attribs=True)
class StepKeyPresent:
    # "Is this symbol present on your keyboard"
    symbol: str
    yes: str
    no: str


@attr.s(auto_attribs=True)
class StepResult:
    # "This is the autodetected layout"
    layout: str
    variant: str


AnyStep = Union[StepPressKey, StepKeyPresent, StepResult]


@attr.s(auto_attribs=True)
class KeyboardSetting:
    layout: str
    variant: str = ''
    toggle: Optional[str] = None


@attr.s(auto_attribs=True)
class KeyboardVariant:
    code: str
    name: str


@attr.s(auto_attribs=True)
class KeyboardLayout:
    code: str
    name: str
    variants: List[KeyboardVariant]


@attr.s(auto_attribs=True)
class KeyboardSetup:
    setting: KeyboardSetting
    layouts: List[KeyboardLayout]


@attr.s(auto_attribs=True)
class SourceSelection:
    name: str
    description: str
    id: str
    size: int
    variant: str
    default: bool


@attr.s(auto_attribs=True)
class SourceSelectionAndSetting:
    sources: List[SourceSelection]
    current_id: str
    search_drivers: bool


@attr.s(auto_attribs=True)
class ZdevInfo:
    id: str
    type: str
    on: bool
    exists: bool
    pers: bool
    auto: bool
    failed: bool
    names: str

    @classmethod
    def from_row(cls, row):
        row = dict((k.split('=', 1) for k in shlex.split(row)))
        for k, v in row.items():
            if v == "yes":
                row[k] = True
            if v == "no":
                row[k] = False
            if k == "pers" and v == "auto":
                row[k] = True
        return ZdevInfo(**row)

    @property
    def typeclass(self):
        if self.type.startswith('zfcp'):
            return 'zfcp'
        return self.type


class WLANSupportInstallState(enum.Enum):
    NOT_NEEDED = enum.auto()
    NOT_AVAILABLE = enum.auto()
    INSTALLING = enum.auto()
    FAILED = enum.auto()
    DONE = enum.auto()


@attr.s(auto_attribs=True)
class NetworkStatus:
    devices: List[NetDevInfo]
    wlan_support_install_state: WLANSupportInstallState


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
    model: Optional[str] = None
    vendor: Optional[str] = None


@attr.s(auto_attribs=True)
class GuidedChoice:
    disk_id: str
    use_lvm: bool = False
    password: Optional[str] = attr.ib(default=None, repr=False)
    use_tpm: bool = False


class StorageEncryptionSupport(enum.Enum):
    DISABLED = 'disabled'
    AVAILABLE = 'available'
    UNAVAILABLE = 'unavailable'
    DEFECTIVE = 'defective'


class StorageSafety(enum.Enum):
    UNSET = 'unset'
    ENCRYPTED = 'encrypted'
    PREFER_ENCRYPTED = 'prefer-encrypted'
    PREFER_UNENCRYPTED = 'prefer-unencrypted'


class EncryptionType(enum.Enum):
    NONE = ''
    CRYPTSETUP = 'cryptsetup'
    DEVICE_SETUP_HOOK = 'device-setup-hook'


@attr.s(auto_attribs=True)
class StorageEncryption:
    support: StorageEncryptionSupport
    storage_safety: StorageSafety = named_field('storage-safety')
    encryption_type: EncryptionType = named_field(
        'encryption-type', default=EncryptionType.NONE)
    unavailable_reason: str = named_field(
        'unavailable-reason', default='')


@attr.s(auto_attribs=True)
class GuidedStorageResponse:
    status: ProbeStatus
    error_report: Optional[ErrorReportRef] = None
    disks: Optional[List[Disk]] = None
    storage_encryption: Optional[StorageEncryption] = None


@attr.s(auto_attribs=True)
class StorageResponse:
    status: ProbeStatus
    error_report: Optional[ErrorReportRef] = None
    bootloader: Optional[Bootloader] = None
    orig_config: Optional[list] = None
    config: Optional[list] = None
    blockdev: Optional[dict] = None
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


@attr.s(auto_attribs=True)
class GuidedResizeValues:
    install_max: int
    minimum: int
    recommended: int
    maximum: int


@attr.s(auto_attribs=True)
class GuidedStorageTargetReformat:
    disk_id: str


@attr.s(auto_attribs=True)
class GuidedStorageTargetResize:
    disk_id: str
    partition_number: int
    new_size: int
    minimum: Optional[int]
    recommended: Optional[int]
    maximum: Optional[int]

    @staticmethod
    def from_recommendations(part, resize_vals):
        return GuidedStorageTargetResize(
                disk_id=part.device.id,
                partition_number=part.number,
                new_size=resize_vals.recommended,
                minimum=resize_vals.minimum,
                recommended=resize_vals.recommended,
                maximum=resize_vals.maximum,
                )


@attr.s(auto_attribs=True)
class GuidedStorageTargetUseGap:
    disk_id: str
    gap: Gap


GuidedStorageTarget = Union[GuidedStorageTargetReformat,
                            GuidedStorageTargetResize,
                            GuidedStorageTargetUseGap]


@attr.s(auto_attribs=True)
class GuidedChoiceV2:
    target: GuidedStorageTarget
    use_lvm: bool = False
    password: Optional[str] = attr.ib(default=None, repr=False)

    @staticmethod
    def from_guided_choice(choice: GuidedChoice):
        return GuidedChoiceV2(
                target=GuidedStorageTargetReformat(disk_id=choice.disk_id),
                use_lvm=choice.use_lvm,
                password=choice.password,
                )


@attr.s(auto_attribs=True)
class GuidedStorageResponseV2:
    status: ProbeStatus
    error_report: Optional[ErrorReportRef] = None
    configured: Optional[GuidedChoiceV2] = None
    possible: List[GuidedStorageTarget] = attr.Factory(list)


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
class IdentityData:
    realname: str = ''
    username: str = ''
    crypted_password: str = attr.ib(default='', repr=False)
    hostname: str = ''


class UsernameValidation(enum.Enum):
    OK = enum.auto()
    ALREADY_IN_USE = enum.auto()
    SYSTEM_RESERVED = enum.auto()
    INVALID_CHARS = enum.auto()
    TOO_LONG = enum.auto()


@attr.s(auto_attribs=True)
class SSHData:
    install_server: bool
    allow_pw: bool
    authorized_keys: List[str] = attr.Factory(list)


class SnapCheckState(enum.Enum):
    FAILED = enum.auto()
    LOADING = enum.auto()
    DONE = enum.auto()


@attr.s(auto_attribs=True)
class ChannelSnapInfo:
    channel_name: str
    revision: str
    confinement: str
    version: str
    size: int
    released_at: datetime.datetime = attr.ib(
        metadata={'time_fmt': '%Y-%m-%dT%H:%M:%S.%fZ'})


@attr.s(auto_attribs=True, eq=False)
class SnapInfo:
    name: str
    summary: str = ''
    publisher: str = ''
    verified: bool = False
    starred: bool = False
    description: str = ''
    confinement: str = ''
    license: str = ''
    channels: List[ChannelSnapInfo] = attr.Factory(list)


@attr.s(auto_attribs=True)
class DriversResponse:
    """ Response to GET request to drivers.
    :install: tells whether third-party drivers will be installed (if any is
    available).
    :drivers: tells what third-party drivers will be installed should we decide
    to do it. It will bet set to None until we figure out what drivers are
    available.
    :local_only: tells if we are looking for drivers only from the ISO.
    :search_drivers: enables or disables drivers listing.
    """
    install: bool
    drivers: Optional[List[str]]
    local_only: bool
    search_drivers: bool


@attr.s(auto_attribs=True)
class DriversPayload:
    install: bool


@attr.s(auto_attribs=True)
class SnapSelection:
    name: str
    channel: str
    classic: bool = False


@attr.s(auto_attribs=True)
class SnapListResponse:
    status: SnapCheckState
    snaps: List[SnapInfo] = attr.Factory(list)
    selections: List[SnapSelection] = attr.Factory(list)


@attr.s(auto_attribs=True)
class TimeZoneInfo:
    timezone: str
    from_geoip: bool


@attr.s(auto_attribs=True)
class UbuntuProInfo:
    token: str = attr.ib(repr=False)


@attr.s(auto_attribs=True)
class UbuntuProResponse:
    """ Response to GET request to /ubuntu_pro """
    token: str = attr.ib(repr=False)
    has_network: bool


class UbuntuProCheckTokenStatus(enum.Enum):
    VALID_TOKEN = enum.auto()
    INVALID_TOKEN = enum.auto()
    EXPIRED_TOKEN = enum.auto()
    UNKNOWN_ERROR = enum.auto()


@attr.s(auto_attribs=True)
class UPCSInitiateResponse:
    """ Response to Ubuntu Pro contract selection initiate request. """
    user_code: str
    validity_seconds: int


class UPCSWaitStatus(enum.Enum):
    SUCCESS = enum.auto()
    TIMEOUT = enum.auto()


@attr.s(auto_attribs=True)
class UPCSWaitResponse:
    """ Response to Ubuntu Pro contract selection wait request. """
    status: UPCSWaitStatus

    contract_token: Optional[str]


@attr.s(auto_attribs=True)
class UbuntuProService:
    name: str
    description: str
    auto_enabled: bool


@attr.s(auto_attribs=True)
class UbuntuProSubscription:
    contract_name: str
    account_name: str
    contract_token: str
    services: List[UbuntuProService]


@attr.s(auto_attribs=True)
class UbuntuProCheckTokenAnswer:
    status: UbuntuProCheckTokenStatus

    subscription: Optional[UbuntuProSubscription]


class ShutdownMode(enum.Enum):
    REBOOT = enum.auto()
    POWEROFF = enum.auto()


@attr.s(auto_attribs=True)
class WSLConfigurationBase:
    automount_root: str = attr.ib(default='/mnt/')
    automount_options: str = ''
    network_generatehosts: bool = attr.ib(default=True)
    network_generateresolvconf: bool = attr.ib(default=True)


@attr.s(auto_attribs=True)
class WSLConfigurationAdvanced:
    automount_enabled:  bool = attr.ib(default=True)
    automount_mountfstab:  bool = attr.ib(default=True)
    interop_enabled:  bool = attr.ib(default=True)
    interop_appendwindowspath: bool = attr.ib(default=True)
    systemd_enabled:  bool = attr.ib(default=False)


# Options that affect the setup experience itself, but won't reflect in the
# /etc/wsl.conf configuration file.
@attr.s(auto_attribs=True)
class WSLSetupOptions:
    install_language_support_packages: bool = attr.ib(default=True)


class TaskStatus(enum.Enum):
    DO = "Do"
    DOING = "Doing"
    DONE = "Done"
    ABORT = "Abort"
    UNDO = "Undo"
    UNDOING = "Undoing"
    HOLD = "Hold"
    ERROR = "Error"


@attr.s(auto_attribs=True)
class TaskProgress:
    label: str = ''
    done: int = 0
    total: int = 0


@attr.s(auto_attribs=True)
class Task:
    id: str
    kind: str
    summary: str
    status: TaskStatus
    progress: TaskProgress = TaskProgress()


@attr.s(auto_attribs=True)
class Change:
    id: str
    kind: str
    summary: str
    status: TaskStatus
    tasks: List[Task]
    ready: bool
    err: Optional[str] = None
    data: Any = None
