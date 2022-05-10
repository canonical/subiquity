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
import pwd
import os
import re
from typing import Set

from subiquitycore.context import with_context

from subiquity.common.apidef import API
from subiquity.common.resources import resource_path
from subiquity.common.types import IdentityData, UsernameValidation
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.identity')

USERNAME_MAXLEN = 32
USERNAME_REGEX = r'[a-z_][a-z0-9_-]*'


def _reserved_names_from_file(path: str) -> Set[str]:
    if os.path.exists(path):
        with open(path, "r") as f:
            return {
                s.split()[0] for line in f.readlines()
                if (s := line.strip()) and not s.startswith("#")
            }
    else:
        return set()


class IdentityController(SubiquityController):

    endpoint = API.identity

    _system_reserved_names = set()
    _existing_usernames = set()
    autoinstall_key = model_name = "identity"
    autoinstall_schema = {
        'type': 'object',
        'properties': {
            'realname': {'type': 'string'},
            'username': {'type': 'string'},
            'hostname': {'type': 'string'},
            'password': {'type': 'string'},
            },
        'required': ['username', 'hostname', 'password'],
        'additionalProperties': False,
        }

    # TODO: Find THE way to initialize application_reserved_names.
    def __init__(self, app):
        super().__init__(app)
        core_reserved_path = resource_path("reserved-usernames")
        self._system_reserved_names = \
            _reserved_names_from_file(core_reserved_path)
        self._system_reserved_names.add('root')

        self._existing_usernames = {
            u.pw_name for u in pwd.getpwall()
        }

    def load_autoinstall_data(self, data):
        if data is not None:
            identity_data = IdentityData(
                realname=data.get('realname', ''),
                username=data['username'],
                hostname=data['hostname'],
                crypted_password=data['password'],
                )
            self.model.add_user(identity_data)

    @with_context()
    async def apply_autoinstall_config(self, context=None):
        if not self.model.user:
            if 'user-data' not in self.app.autoinstall_config:
                raise Exception("no identity data provided")

    def make_autoinstall(self):
        if self.model.user is None:
            return {}
        r = attr.asdict(self.model.user)
        r['hostname'] = self.model.hostname
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
        self.model.add_user(data)
        if await self.validate_username_GET(data.username) != \
                UsernameValidation.OK:
            log.error("Username <%s> is invalid and should not be submitted.",
                      data.username)
        await self.configured()

    async def validate_username_GET(self, username: str) -> UsernameValidation:
        if username in self._existing_usernames:
            return UsernameValidation.ALREADY_IN_USE

        if username in self._system_reserved_names:
            return UsernameValidation.SYSTEM_RESERVED

        if not re.match(USERNAME_REGEX, username):
            return UsernameValidation.INVALID_CHARS

        if len(username) > USERNAME_MAXLEN:
            return UsernameValidation.TOO_LONG

        return UsernameValidation.OK
