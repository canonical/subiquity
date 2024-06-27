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

""" Types defined in this module are deprecated and will at some point be
replaced by `attr.s` structures or similar. """


import typing
from typing import Any, TypedDict

try:
    from typing import Required
except ImportError:
    # For compability with Python < 3.11.
    # TODO Keep only what is in the try block when switching to core24.
    class Required(typing.Generic[typing.TypeVar("T")]):
        pass


from subiquity.models.filesystem import (
    Disk,
    Partition,
    Raid,
    RaidLevel,
    RecoveryKeyHandler,
)


class RaidSpec(TypedDict):
    name: str
    level: RaidLevel
    devices: set[Any]
    spare_devices: set[Any]


VolGroupSpec = TypedDict(
    "VolGroupSpec",
    {
        "name": Required[str],
        "devices": set[Disk | Partition | Raid],
        "passphrase": str,
        "recovery-key": RecoveryKeyHandler,
    },
    total=False,
)


FileSystemSpec = TypedDict(
    "FileSystemSpec",
    {
        "fstype": str | None,  # Sometimes, we explicitly do fstype=None
        "mount": str | None,
        "wipe": str | None,  # NOTE: no wipe is different from wipe=None
        "use_swap": bool,
        "on-remote-storage": bool,
    },
    total=False,
)


class LogicalVolumeSpec(FileSystemSpec, total=False):
    name: str
    size: int


class PartitionSpec(FileSystemSpec, total=False):
    size: int
