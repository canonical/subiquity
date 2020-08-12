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
from typing import List

import attr


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
class IdentityData:
    realname: str = ''
    username: str = ''
    crypted_password: str = attr.ib(default='', repr=False)
    hostname: str = ''


@attr.s(auto_attribs=True)
class SSHData:
    install_server: str
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
    size: str
    released_at: datetime.datetime


@attr.s(auto_attribs=True, cmp=False)
class SnapInfo:
    name: str
    summary: str = ''
    publisher: str = ''
    verified: str = ''
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
class SnapListData:
    status: SnapCheckState
    snaps: List[SnapInfo] = attr.Factory(list)
    selections: List[SnapSelection] = attr.Factory(list)
