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

from subiquity.common.apidef import API
from subiquity.server.controller import SubiquityController
from subiquity.server.curtin import run_curtin_command
from subiquity.server.types import InstallerChannels

log = logging.getLogger('subiquity.server.controllers.drivers')


class DriversController(SubiquityController):

    endpoint = API.drivers

    autoinstall_key = model_name = "drivers"
    autoinstall_schema = {
        'type': 'object',
        'properties': {
            'install': {
                'type': 'boolean',
            },
        },
    }
    autoinstall_default = {"install": False}

    has_drivers = None

    def make_autoinstall(self):
        return {
            "install": self.model.do_install,
        }

    def load_autoinstall_data(self, data):
        if data is not None and "install" in data:
            self.model.do_install = data["install"]

    def start(self):
        self._wait_apt = asyncio.Event()
        self.app.hub.subscribe(
            InstallerChannels.APT_CONFIGURED,
            self._wait_apt.set)
        self._drivers_task = asyncio.create_task(self._list_drivers())

    @with_context()
    async def _list_drivers(self, context):
        with context.child("wait_apt"):
            await self._wait_apt.wait()
        apt = self.app.controllers.Mirror.apt_configurer
        cmd = ['ubuntu-drivers', 'list']
        if self.app.base_model.source.current.variant == 'server':
            cmd.append('--gpgpu')
        if self.app.opts.dry_run:
            if 'has-drivers' in self.app.debug_flags:
                self.has_drivers = True
                return
            elif 'run-drivers' in self.app.debug_flags:
                pass
            else:
                self.has_drivers = False
                await self.configured()
                return
        async with apt.overlay() as d:
            result = await run_curtin_command(
                self.app, context, "in-target", "-t", d.mountpoint,
                "--", *cmd, capture=True)
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
