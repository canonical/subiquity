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
from typing import Optional

from subiquitycore.context import with_context
from subiquitycore.utils import arun_command

from subiquity.common.apidef import API
from subiquity.server.controller import SubiquityController
from subiquity.server.types import InstallerChannels

log = logging.getLogger('subiquity.server.controllers.drivers')


class DriversController(SubiquityController):

    endpoint = API.drivers

    autoinstall_key = model_name = "drivers"
    autoinstall_schema = {
        'type': 'boolean',
    }
    autoinstall_default = False

    has_drivers = None

    def make_autoinstall(self):
        return self.model.do_install

    def load_autoinstall_data(self, data):
        self.model.do_install = data

    def start(self):
        self.app.hub.subscribe(
            InstallerChannels.APT_CONFIGURED,
            self._wait_apt_configured)

    def _wait_apt_configured(self):
        self._drivers_task = asyncio.create_task(self._list_drivers())

    @with_context()
    async def _list_drivers(self, context):
        path = self.app.controllers.Install.for_install_path
        cmd = ['chroot', path, 'ubuntu-drivers', 'list']
        if self.app.base_model.source.current.variant == 'server':
            cmd.append('--gpgpu')
        if self.app.opts.dry_run:
            del cmd[:2]
        result = await arun_command(cmd)
        self.has_drivers = bool(result.stdout.strip())
        if not self.has_drivers:
            await self.configured()

    async def GET(self, wait: bool = False) -> Optional[bool]:
        if wait:
            await self._drivers_task
        return self.has_drivers

    async def POST(self, install: bool):
        self.model.do_install = install
        await self.configured()
