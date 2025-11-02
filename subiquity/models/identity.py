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

import attr

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


class IdentityModel:
    """Model representing user identity"""

    def __init__(self) -> None:
        self._user: User | None = None
        self._hostname: str | None = None

    def add_user(self, identity_data) -> None:
        self._hostname = identity_data.hostname
        d = {}
        d["realname"] = identity_data.realname
        d["username"] = identity_data.username
        d["password"] = identity_data.crypted_password
        if not d["realname"]:
            d["realname"] = identity_data.username
        d["groups"] = {DefaultGroups}
        self._user = User(**d)

    @property
    def hostname(self) -> str | None:
        return self._hostname

    @property
    def user(self) -> User | None:
        return self._user

    def __repr__(self):
        return "<LocalUser: {} {}>".format(self.user, self.hostname)
