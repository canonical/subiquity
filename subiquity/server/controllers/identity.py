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
import re
from typing import Set

import attr

from subiquity.common.apidef import API
from subiquity.common.resources import resource_path
from subiquity.common.types import IdentityData, UsernameValidation
from subiquity.server.autoinstall import AutoinstallError
from subiquity.server.controller import SubiquityController

log = logging.getLogger("subiquity.server.controllers.identity")

USERNAME_MAXLEN = 32
USERNAME_REGEX = r"[a-z_][a-z0-9_-]*"


def _reserved_names_from_file(path: str) -> Set[str]:
    names = set()
    # The absence of this file is an installer bug.
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            names.add(line.split()[0])

    return names


class IdentityController(SubiquityController):
    endpoint = API.identity

    autoinstall_key = model_name = "identity"
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "realname": {"type": "string"},
            "username": {"type": "string"},
            "hostname": {"type": "string"},
            "password": {"type": "string"},
        },
        "required": ["username", "hostname", "password"],
        "additionalProperties": False,
    }

    interactive_for_variants = {"desktop", "server"}

    def __init__(self, app):
        super().__init__(app)
        core_reserved_path = resource_path("reserved-usernames")
        self._system_reserved_names = _reserved_names_from_file(core_reserved_path)

        # Let this field be the customisation point for variants.
        self.existing_usernames = {"root"}

    def load_autoinstall_data(self, data):
        if data is not None:
            identity_data = IdentityData(
                realname=data.get("realname", ""),
                username=data["username"],
                hostname=data["hostname"],
                crypted_password=data["password"],
            )
            self.model.add_user(identity_data)
            return

        # The identity section is required except if (any):
        # 1. a user-data section is provided
        if "user-data" in self.app.autoinstall_config:
            return
        # 2. we are installing not-Server (Desktop)
        if self.app.base_model.source.current.variant != "server":
            return
        # 3. we are only refreshing the reset partition
        # (The identity controller doesn't figure this out until the apply
        # step, so we are going to cheat and inspect the situation here)
        storage_config = self.app.autoinstall_config.get("storage")
        if (
            storage_config is not None
            and storage_config.get("layout") is not None
            and storage_config["layout"].get("reset-partition-only")
        ):
            return
        # 4. identity section is interactive
        if self.interactive():
            return
        raise AutoinstallError("neither identity nor user-data provided")

    def make_autoinstall(self):
        if self.model.user is None:
            return {}
        r = attr.asdict(self.model.user)
        r["hostname"] = self.model.hostname
        return r

    async def GET(self) -> IdentityData:
        data = IdentityData()
        if self.model.user is not None:
            data.username = self.model.user.username
            data.realname = self.model.user.realname
        if self.model.hostname:
            data.hostname = self.model.hostname
        return data

    async def POST(self, data: IdentityData):
        validated = await self.validate_username_GET(data.username)
        if validated != UsernameValidation.OK:
            raise ValueError(
                "Username <{}> is invalid and should not be submitted.".format(
                    data.username
                ),
                validated,
            )

        self.model.add_user(data)
        await self.configured()

    async def validate_username_GET(self, username: str) -> UsernameValidation:
        if username in self.existing_usernames:
            return UsernameValidation.ALREADY_IN_USE

        if username in self._system_reserved_names:
            return UsernameValidation.SYSTEM_RESERVED

        if not re.fullmatch(USERNAME_REGEX, username):
            return UsernameValidation.INVALID_CHARS

        if len(username) > USERNAME_MAXLEN:
            return UsernameValidation.TOO_LONG

        return UsernameValidation.OK
