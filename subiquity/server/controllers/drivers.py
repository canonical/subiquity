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
from typing import List, Optional

from subiquitycore.context import with_context

from subiquity.common.apidef import API
from subiquity.common.types import DriversPayload, DriversResponse
from subiquity.server.controller import SubiquityController
from subiquity.server.types import InstallerChannels
from subiquity.server.ubuntu_drivers import (
    CommandNotFoundError,
    UbuntuDriversInterface,
    get_ubuntu_drivers_interface,
    )

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

    drivers: Optional[List[str]] = None

    def __init__(self, app) -> None:
        super().__init__(app)
        self.ubuntu_drivers: UbuntuDriversInterface = \
            get_ubuntu_drivers_interface(app)

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
        async with apt.overlay() as d:
            try:
                # Make sure ubuntu-drivers is available.
                self.ubuntu_drivers.ensure_cmd_exists(d.mountpoint)
            except CommandNotFoundError:
                self.drivers = []
            else:
                self.drivers = await self.ubuntu_drivers.list_drivers(
                    root_dir=d.mountpoint,
                    context=context)
        log.debug("Available drivers to install: %s", self.drivers)
        if not self.drivers:
            await self.configured()
        else:
            # TODO Remove this once we have the GUI controller.
            await self.POST(install=True)

    async def GET(self, wait: bool = False) -> DriversResponse:
        if wait:
            await self._drivers_task
        return DriversResponse(install=self.model.do_install,
                               drivers=self.drivers)

    async def POST(self, data: DriversPayload) -> None:
        self.model.do_install = data.install
        await self.configured()
