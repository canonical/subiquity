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

"""This module defines types that are used in the API between the client and
server processes.  View code should only use these types!"""

import datetime
import enum
import shlex
from typing import Any, Dict, List, Optional, Union

import attr

from subiquity.server.nonreportable import NonReportableException
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


@attr.s(auto_attribs=True)
class NonReportableError:
    cause: str
    message: str
    details: Optional[str]

    @classmethod
    def from_exception(cls, exc: NonReportableException):
        return cls(
            cause=type(exc).__name__,
            message=str(exc),
            details=exc.details,
        )


class ApplicationState(enum.Enum):
    """Represents the state of the application at a given time."""

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

    # State reported while unattended-upgrades is running.
    # TODO: check if this should be dropped in favor of RUNNING.
    UU_RUNNING = enum.auto()

    LATE_COMMANDS = enum.auto()

    # Final state
    DONE = enum.auto()
    ERROR = enum.auto()
    EXITED = enum.auto()


@attr.s(auto_attribs=True)
class ApplicationStatus:
    state: ApplicationState
    confirming_tty: str
    error: Optional[ErrorReportRef]
    nonreportable_error: Optional[NonReportableError]
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
    current_snap_version: str = ""
    new_snap_version: str = ""


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
    # This data structure represents a subset of the XKB options.
    # As explained in the XKB configuration guide, XkbLayout and
    # XkbVariant can hold multiple comma-separated values.
    # http://www.xfree86.org/current/XKB-Config2.html#4
    # Ideally, we would internally represent a keyboard setting as a
    # toggle + a list of [layout, variant].
    layout: str
    variant: str = ""
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
        row = dict((k.split("=", 1) for k in shlex.split(row)))
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
        if self.type.startswith("zfcp"):
            return "zfcp"
        return self.type


class PackageInstallState(enum.Enum):
    NOT_NEEDED = enum.auto()
    NOT_AVAILABLE = enum.auto()
    INSTALLING = enum.auto()
    FAILED = enum.auto()
    DONE = enum.auto()


@attr.s(auto_attribs=True)
class NetworkStatus:
    devices: List[NetDevInfo]
    wlan_support_install_state: PackageInstallState


@attr.s(auto_attribs=True)
class IdentityData:
    realname: str = ""
    username: str = ""
    crypted_password: str = attr.ib(default="", repr=False)
    hostname: str = ""


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


@attr.s(auto_attribs=True)
class SSHIdentity:
    """Represents a SSH identity (public key + fingerprint)."""

    key_type: str
    key: str
    key_comment: str
    key_fingerprint: str

    def to_authorized_key(self):
        return f"{self.key_type} {self.key} {self.key_comment}"


class SSHFetchIdStatus(enum.Enum):
    OK = enum.auto()
    IMPORT_ERROR = enum.auto()
    FINGERPRINT_ERROR = enum.auto()


@attr.s(auto_attribs=True)
class SSHFetchIdResponse:
    status: SSHFetchIdStatus
    identities: Optional[List[SSHIdentity]]
    error: Optional[str]


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
        metadata={"time_fmt": "%Y-%m-%dT%H:%M:%S.%fZ"}
    )


@attr.s(auto_attribs=True, eq=False)
class SnapInfo:
    name: str
    summary: str = ""
    publisher: str = ""
    verified: bool = False
    starred: bool = False
    description: str = ""
    confinement: str = ""
    license: str = ""
    channels: List[ChannelSnapInfo] = attr.Factory(list)


@attr.s(auto_attribs=True)
class DriversResponse:
    """Response to GET request to drivers.
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
class OEMResponse:
    metapackages: Optional[List[str]]


@attr.s(auto_attribs=True)
class CodecsData:
    install: bool


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
    """Response to GET request to /ubuntu_pro"""

    token: str = attr.ib(repr=False)
    has_network: bool


class UbuntuProCheckTokenStatus(enum.Enum):
    VALID_TOKEN = enum.auto()
    INVALID_TOKEN = enum.auto()
    EXPIRED_TOKEN = enum.auto()
    UNKNOWN_ERROR = enum.auto()


@attr.s(auto_attribs=True)
class UbuntuProGeneralInfo:
    eol_esm_year: Optional[int]
    universe_packages: int
    main_packages: int


@attr.s(auto_attribs=True)
class UPCSInitiateResponse:
    """Response to Ubuntu Pro contract selection initiate request."""

    user_code: str
    validity_seconds: int


class UPCSWaitStatus(enum.Enum):
    SUCCESS = enum.auto()
    TIMEOUT = enum.auto()


@attr.s(auto_attribs=True)
class UPCSWaitResponse:
    """Response to Ubuntu Pro contract selection wait request."""

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
    label: str = ""
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


class CasperMd5Results(enum.Enum):
    UNKNOWN = "unknown"
    FAIL = "fail"
    PASS = "pass"
    SKIP = "skip"


class MirrorCheckStatus(enum.Enum):
    OK = "OK"
    RUNNING = "RUNNING"
    FAILED = "FAILED"


@attr.s(auto_attribs=True)
class MirrorCheckResponse:
    url: str
    status: MirrorCheckStatus
    output: str


@attr.s(auto_attribs=True)
class MirrorPost:
    elected: Optional[str] = None
    candidates: Optional[List[str]] = None
    staged: Optional[str] = None
    use_during_installation: Optional[bool] = None


class MirrorPostResponse(enum.Enum):
    OK = "ok"
    NO_USABLE_MIRROR = "no-usable-mirror"


@attr.s(auto_attribs=True)
class MirrorGet:
    relevant: bool
    elected: Optional[str]
    candidates: List[str]
    staged: Optional[str]
    # Tells whether the mirror will be used during the installation.
    # When it is False, we will only fetch packages from the pool.
    use_during_installation: bool


class MirrorSelectionFallback(enum.Enum):
    ABORT = "abort"
    CONTINUE_ANYWAY = "continue-anyway"
    OFFLINE_INSTALL = "offline-install"


@attr.s(auto_attribs=True)
class AdConnectionInfo:
    admin_name: str = ""
    domain_name: str = ""
    password: str = attr.ib(repr=False, default="")


class AdAdminNameValidation(enum.Enum):
    OK = "OK"
    EMPTY = "Empty"
    INVALID_CHARS = "Contains invalid characters"


class AdDomainNameValidation(enum.Enum):
    OK = "OK"
    EMPTY = "Empty"
    TOO_LONG = "Too long"
    INVALID_CHARS = "Contains invalid characters"
    START_DOT = "Starts with a dot"
    END_DOT = "Ends with a dot"
    START_HYPHEN = "Starts with a hyphen"
    END_HYPHEN = "Ends with a hyphen"
    MULTIPLE_DOTS = "Contains multiple dots"
    REALM_NOT_FOUND = "Could not find the domain controller"


class AdPasswordValidation(enum.Enum):
    OK = "OK"
    EMPTY = "Empty"


class AdJoinResult(enum.Enum):
    OK = "OK"
    JOIN_ERROR = "Failed to join"
    EMPTY_HOSTNAME = "Target hostname cannot be empty"
    PAM_ERROR = "Failed to update pam-auth"
    UNKNOWN = "Didn't attempt to join yet"
