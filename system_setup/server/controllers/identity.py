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

from subiquity.common.types import IdentityData
from subiquity.server.controllers.identity import IdentityController

log = logging.getLogger('system_setup.server.controllers.identity')


class WSLIdentityController(IdentityController):

    autoinstall_schema = {
        'type': 'object',
        'properties': {
            'realname': {'type': 'string'},
            'username': {'type': 'string'},
            'password': {'type': 'string'},
            },
        'required': ['username', 'password'],
        'additionalProperties': False,
        }

    def load_autoinstall_data(self, data):
        if data is not None:
            identity_data = IdentityData(
                realname=data.get('realname', ''),
                username=data['username'],
                crypted_password=data['password'],
                )
            self.model.add_user(identity_data)

    def make_autoinstall(self):
        if self.model.user is None:
            return {}
        r = attr.asdict(self.model.user)
        return r

    async def GET(self) -> IdentityData:
        data = IdentityData()
        if self.model.user is not None:
            data.username = self.model.user.username
            data.realname = self.model.user.realname
        return data
