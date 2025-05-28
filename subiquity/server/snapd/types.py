# Copyright 2022 Canonical, Ltd.
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

import enum
from typing import Dict, List, Optional

import attr

from subiquity.common.serialize import NonExhaustive, named_field
from subiquity.common.types.storage import GuidedChoiceV2

RFC3339 = "%Y-%m-%dT%H:%M:%S.%fZ"


def date_field(name=None, default=attr.NOTHING):
    metadata = {"time_fmt": RFC3339}
    if name is not None:
        metadata.update(named_field(name).metadata)
    return attr.ib(metadata=metadata, default=default)


ChangeID = str


def _underscore_to_hyphen(cls, fields):
    results = []
    for field in fields:
        metadata = field.metadata | {"name": field.name.replace("_", "-")}
        results.append(field.evolve(metadata=metadata))
    return results


def snapdtype(cls):
    return attr.s(
        auto_attribs=True, kw_only=True, field_transformer=_underscore_to_hyphen
    )(cls)


class SnapStatus(enum.Enum):
    ACTIVE = "active"
    AVAILABLE = "available"


@snapdtype
class Publisher:
    id: str
    username: str
    display_name: str


@snapdtype
class Snap:
    id: str
    name: str
    status: SnapStatus
    version: str
    revision: str
    channel: str
    publisher: Optional[Publisher] = None


class SnapAction(enum.Enum):
    REFRESH = "refresh"
    SWITCH = "switch"


@snapdtype
class SnapActionRequest:
    action: SnapAction
    channel: str = ""
    ignore_running: bool = False


class ResponseType:
    SYNC = "sync"
    ASYNC = "async"
    ERROR = "error"


@snapdtype
class Response:
    type: str
    status_code: int
    status: str


class Role(enum.Enum):
    NONE = ""
    MBR = "mbr"
    SYSTEM_BOOT = "system-boot"
    SYSTEM_DATA = "system-data"


@snapdtype
class RelativeOffset:
    relative_to: str
    offset: int


@snapdtype
class VolumeContent:
    source: str = ""
    target: str = ""
    image: str = ""
    offset: Optional[int] = None
    offset_write: Optional[RelativeOffset] = None
    size: int = 0
    unpack: bool = False


@snapdtype
class VolumeUpdate:
    edition: int = 0
    preserve: Optional[List[str]] = None


@snapdtype
class VolumeStructure:
    name: str = ""
    filesystem_label: str = ""
    offset: Optional[int] = None
    offset_write: Optional[RelativeOffset] = None
    size: int = 0
    type: str = ""
    role: NonExhaustive[Role] = Role.NONE
    id: Optional[str] = None
    filesystem: str = ""
    content: Optional[List[VolumeContent]] = None
    update: VolumeUpdate = attr.Factory(VolumeUpdate)

    def gpt_part_type_uuid(self):
        if "," in self.type:
            return self.type.split(",", 1)[1].upper()
        else:
            return self.type


@snapdtype
class Volume:
    schema: str = ""
    bootloader: str = ""
    id: str = ""
    structure: Optional[List[VolumeStructure]] = None


@snapdtype
class OnVolumeStructure(VolumeStructure):
    device: Optional[str] = None

    @classmethod
    def from_volume_structure(cls, vs: VolumeStructure):
        return cls(**attr.asdict(vs, recurse=False))


@snapdtype
class OnVolume(Volume):
    structure: Optional[List[OnVolumeStructure]] = None

    @classmethod
    def from_volume(cls, v: Volume):
        kw = attr.asdict(v, recurse=False)
        kw["structure"] = [
            OnVolumeStructure.from_volume_structure(vs) for vs in v.structure
        ]
        return cls(**kw)


class StorageEncryptionSupport(enum.Enum):
    DISABLED = "disabled"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEFECTIVE = "defective"


class StorageSafety(enum.Enum):
    UNSET = "unset"
    ENCRYPTED = "encrypted"
    PREFER_ENCRYPTED = "prefer-encrypted"
    PREFER_UNENCRYPTED = "prefer-unencrypted"


class EncryptionType(enum.Enum):
    NONE = ""
    CRYPTSETUP = "cryptsetup"
    DEVICE_SETUP_HOOK = "device-setup-hook"


@snapdtype
class StorageEncryption:
    support: StorageEncryptionSupport
    storage_safety: StorageSafety
    encryption_type: EncryptionType = EncryptionType.NONE
    unavailable_reason: str = ""


@snapdtype
class AvailableOptional:
    snaps: List[str] = attr.Factory(list)
    components: Dict[str, List[str]] = attr.Factory(dict)


class ModelSnapType(enum.Enum):
    KERNEL = "kernel"
    GADGET = "gadget"
    BASE = "base"
    SNAPD = "snapd"
    APP = "app"


class PresenceValue(enum.Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"


@snapdtype
class Presence:
    presence: PresenceValue


@snapdtype
class ModelSnap:
    default_channel: str
    id: str
    name: str
    type: NonExhaustive[ModelSnapType]
    components: Optional[Dict[str, Presence]] = None
    presence: PresenceValue = PresenceValue.REQUIRED


@snapdtype
class Model:
    architecture: str
    snaps: List[ModelSnap]

    def snaps_of_type(self, typ: ModelSnapType) -> List[ModelSnap]:
        return [snap for snap in self.snaps if snap.type == typ]


@snapdtype
class ShortSystemDetails:
    label: str
    current: bool = False
    volumes: Dict[str, Volume] = attr.Factory(dict)
    storage_encryption: Optional[StorageEncryption] = None


@snapdtype
class SystemDetails(ShortSystemDetails):
    model: Model
    available_optional: Optional[AvailableOptional] = None


@snapdtype
class SystemsResponse:
    systems: List[ShortSystemDetails] = attr.Factory(list)


class SystemAction(enum.Enum):
    INSTALL = "install"
    CHECK_PASSPHRASE = "check-passphrase"
    CHECK_PIN = "check-pin"


class SystemActionStep(enum.Enum):
    SETUP_STORAGE_ENCRYPTION = "setup-storage-encryption"
    FINISH = "finish"


# Setting all=True and with a non-empty AvailableOptional will result in an
# error, so set all=False by default.
@snapdtype
class OptionalInstall(AvailableOptional):
    all: bool = False


class VolumesAuthMode(enum.Enum):
    PIN = "pin"
    PASSPHRASE = "passphrase"


@snapdtype
class VolumesAuth:
    mode: VolumesAuthMode
    passphrase: Optional[str] = None
    pin: Optional[str] = None
    # kdf-time: Optional[int]
    # kdf-type: Optional["argon2id"|"argon2i"|"pbkdf2"]

    @classmethod
    def from_choice(cls, choice: GuidedChoiceV2) -> Optional["VolumesAuth"]:
        if choice.password is not None:
            return cls(mode=VolumesAuthMode.PASSPHRASE, passphrase=choice.password)
        elif choice.pin is not None:
            return cls(mode=VolumesAuthMode.PIN, pin=choice.pin)
        else:
            return None


@snapdtype
class SystemActionRequest:
    action: Optional[SystemAction] = None
    step: Optional[SystemActionStep] = None
    on_volumes: Optional[Dict[str, OnVolume]] = None
    # When optional_install=None it is equivalent to OptionalInstall(all=True)
    optional_install: Optional[OptionalInstall] = None
    volumes_auth: Optional[VolumesAuth] = None


@snapdtype
class SystemActionResponse:
    encrypted_devices: Dict[NonExhaustive[Role], str] = attr.Factory(dict)


class EntropyCheckResponseKind(enum.Enum):
    INVALID_PIN = "invalid-pin"
    INVALID_PASSPHRASE = "invalid-passphrase"
    UNSUPPORTED = "unsupported"


class InsufficientEntropyReasons(enum.Enum):
    LOW_ENTROPY = "low-entropy"


@snapdtype
class InsufficientEntropyDetails:
    reasons: List[InsufficientEntropyReasons]
    entropy_bits: float
    min_entropy_bits: float


@snapdtype
class EntropyCheckResponse:
    kind: Optional[EntropyCheckResponseKind] = None
    message: Optional[str] = None
    value: Optional[InsufficientEntropyDetails] = None
