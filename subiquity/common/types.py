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
from typing import Dict, List, Optional, Union

import attr

from subiquitycore.models.network import NetDevInfo


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
    STARTING_UP = enum.auto()
    CLOUD_INIT_WAIT = enum.auto()
    EARLY_COMMANDS = enum.auto()
    WAITING = enum.auto()
    NEEDS_CONFIRMATION = enum.auto()
    RUNNING = enum.auto()
    POST_WAIT = enum.auto()
    POST_RUNNING = enum.auto()
    UU_RUNNING = enum.auto()
    UU_CANCELLING = enum.auto()
    DONE = enum.auto()
    ERROR = enum.auto()


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
class Partition:
    size: int
    number: int
    annotations: List[str]


@attr.s(auto_attribs=True)
class Disk:
    id: str
    label: str
    type: str
    size: int
    usage_labels: List[str]
    partitions: List[Partition]
    ok_for_guided: bool


@attr.s(auto_attribs=True)
class GuidedChoice:
    disk_id: str
    use_lvm: bool = False
    password: Optional[str] = attr.ib(default=None, repr=False)


@attr.s(auto_attribs=True)
class GuidedStorageResponse:
    status: ProbeStatus
    error_report: Optional[ErrorReportRef] = None
    disks: Optional[List[Disk]] = None


@attr.s(auto_attribs=True)
class StorageResponse:
    status: ProbeStatus
    error_report: Optional[ErrorReportRef] = None
    bootloader: Optional[Bootloader] = None
    orig_config: Optional[list] = None
    config: Optional[list] = None
    blockdev: Optional[dict] = None
    dasd: Optional[dict] = None


@attr.s(auto_attribs=True)
class IdentityData:
    realname: str = ''
    username: str = ''
    crypted_password: str = attr.ib(default='', repr=False)
    hostname: str = ''


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


@attr.s(auto_attribs=True, cmp=False)
class SnapInfo:
    name: str
    summary: str = ''
    publisher: str = ''
    verified: bool = False
    description: str = ''
    confinement: str = ''
    license: str = ''
    channels: List[ChannelSnapInfo] = attr.Factory(list)


@attr.s(auto_attribs=True)
class SnapSelection:
    name: str
    channel: str
    is_classic: bool = False


@attr.s(auto_attribs=True)
class SnapListResponse:
    status: SnapCheckState
    snaps: List[SnapInfo] = attr.Factory(list)
    selections: List[SnapSelection] = attr.Factory(list)


@attr.s(auto_attribs=True)
class TimeZoneInfo:
    timezone: str
    from_geoip: bool


class WSLConfiguration1Data:
    custom_path: str = attr.ib(default='/mnt/')
    custom_mount_opt: str = ''
    gen_host: bool = attr.ib(default=True)
    gen_resolvconf: bool = attr.ib(default=True)


class LookType(enum.Enum):
    Default = "default"
    Light = "light"
    Dark = "dark"


@attr.s(auto_attribs=True)
class WSLConfiguration2Data:
    gui_theme: LookType = attr.ib(default=LookType.Default)
    gui_followwintheme: bool = attr.ib(default=True)
    legacy_gui: bool = attr.ib(default=False)
    legacy_audio: bool = attr.ib(default=False)
    adv_ip_detect: bool = attr.ib(default=False)
    wsl_motd_news: bool = attr.ib(default=True)
    automount:  bool = attr.ib(default=True)
    mountfstab:  bool = attr.ib(default=True)
    custom_path: str = attr.ib(default='/mnt/')
    custom_mount_opt: str = ''
    gen_host: bool = attr.ib(default=True)
    gen_resolvconf: bool = attr.ib(default=True)
    interop_enabled:  bool = attr.ib(default=True)
    interop_appendwindowspath: bool = attr.ib(default=True)
