# Copyright 2015-2021 Canonical, Ltd.
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

from subiquity.client.controllers import IdentityController
from subiquity.common.types import IdentityData
from system_setup.ui.views import WSLIdentityView

log = logging.getLogger('system_setup.client.controllers.identity')


class WSLIdentityController(IdentityController):

    async def make_ui(self):
        data = await self.endpoint.GET()
        return WSLIdentityView(self, data)

    def run_answers(self):
        if all(elem in self.answers for elem in
               ['realname', 'username', 'password']):
            identity = IdentityData(
                realname=self.answers['realname'],
                username=self.answers['username'],
                crypted_password=self.answers['password'])
            self.done(identity)
