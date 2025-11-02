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

import logging
from typing import Any

import attr

from subiquity.common.types import IdentityData
from subiquity.server.autoinstall import AutoinstallError

log = logging.getLogger("subiquity.models.identity")


class DefaultGroups:
    """Special value for unresolved default groups"""


@attr.s(auto_attribs=True)
class User:
    realname: str
    username: str
    password: str

    groups: set[str | type[DefaultGroups]]

    def resolved_groups(self, *, default: set[str]) -> set[str]:
        groups = self.groups.copy()
        if DefaultGroups in groups:
            groups.remove(DefaultGroups)
            groups.update(default)
        return groups

    @classmethod
    def from_identity_data(cls, data: IdentityData) -> "User":
        return cls(
            username=data.username,
            password=data.crypted_password,
            realname=data.realname if data.realname else data.username,
            groups={DefaultGroups},
        )

    @classmethod
    def from_autoinstall(cls, data: dict[str, Any]) -> "User":
        if "groups" not in data:
            groups = {DefaultGroups}
        elif isinstance(data["groups"], list):
            groups = set(data["groups"])
        elif isinstance(data["groups"], dict):
            if "override" in data["groups"] and "append" in data["groups"]:
                raise AutoinstallError(
                    "cannot combine `groups: append` and `groups: override`"
                )
            if "override" in data["groups"]:
                groups = set(data["groups"]["override"])
            elif "append" in data["groups"]:
                groups = {DefaultGroups}
                groups.update(set(data["groups"]["append"]))
            else:
                raise ValueError
        else:
            raise ValueError
        return cls(
            username=data["username"],
            realname=data.get("realname", ""),
            password=data["password"],
            groups=groups,
        )

    def to_autoinstall(self) -> dict[str, Any]:
        d = {
            "realname": self.realname,
            "username": self.username,
            "password": self.password,
        }

        if self.groups == {DefaultGroups}:
            # This is the default
            pass
        elif DefaultGroups in self.groups:
            d["groups"] = {"append": sorted(self.groups - {DefaultGroups})}
        else:
            d["groups"] = {"override": sorted(self.groups)}
        return d


class IdentityModel:
    """Model representing user identity"""

    def __init__(self) -> None:
        self.user: User | None = None
        self.hostname: str | None = None

    def add_user(self, data: IdentityData) -> None:
        self.hostname = data.hostname
        self.user = User.from_identity_data(data)

    def __repr__(self):
        return "<LocalUser: {} {}>".format(self.user, self.hostname)
