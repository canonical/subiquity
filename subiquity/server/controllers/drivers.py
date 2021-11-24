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

import asyncio
import logging

from subiquity.common.apidef import API
from subiquity.server.controller import SubiquityController


log = logging.getLogger('subiquity.server.controllers.drivers')


class DriversController(SubiquityController):

    endpoint = API.drivers

    autoinstall_key = model_name = "drivers"
    autoinstall_schema = {
        'type': 'boolean',
    }
    autoinstall_default = False

    def make_autoinstall(self):
        return self.model.do_install

    def load_autoinstall_data(self, data):
        self.model.do_install = data

    def start(self):
        asyncio.create_task(self.configured())

    async def GET(self, wait: bool = False) -> bool:
        return False

    async def POST(self, install: bool):
        self.model.do_install = install
        await self.configured()
