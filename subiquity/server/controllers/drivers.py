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

from subiquity.common.apidef import API
from subiquity.common.types import DriversPayload, DriversResponse
from subiquity.server.apt import OverlayCleanupError
from subiquity.server.controller import SubiquityController
from subiquity.server.types import InstallerChannels
from subiquity.server.ubuntu_drivers import (
    CommandNotFoundError,
    UbuntuDriversInterface,
    get_ubuntu_drivers_interface,
)
from subiquitycore.context import with_context

log = logging.getLogger("subiquity.server.controllers.drivers")


class DriversController(SubiquityController):
    endpoint = API.drivers

    autoinstall_key = model_name = "drivers"
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "install": {
                "type": "boolean",
            },
        },
    }
    autoinstall_default = {"install": False}

    def __init__(self, app) -> None:
        super().__init__(app)
        self.ubuntu_drivers: Optional[UbuntuDriversInterface] = None

        self._list_drivers_task: Optional[asyncio.Task] = None
        self.list_drivers_done_event = asyncio.Event()

        # None means that the list has not (yet) been retrieved whereas an
        # empty list means that no drivers are available.
        self.drivers: Optional[List[str]] = None

    def make_autoinstall(self):
        return {
            "install": self.model.do_install,
        }

    def load_autoinstall_data(self, data):
        if data is not None and "install" in data:
            self.model.do_install = data["install"]

    def start(self):
        self._wait_apt = asyncio.Event()
        self.app.hub.subscribe(InstallerChannels.APT_CONFIGURED, self._wait_apt.set)
        self.app.hub.subscribe(
            (InstallerChannels.CONFIGURED, "source"), self.restart_querying_drivers_list
        )

    def restart_querying_drivers_list(self):
        """Start querying the list of available drivers. This method can be
        invoked multiple times so we need to stop ongoing operations if the
        variant changes."""

        self.ubuntu_drivers = get_ubuntu_drivers_interface(self.app)

        self.drivers = None
        self.list_drivers_done_event.clear()
        if self._list_drivers_task is not None:
            self._list_drivers_task.cancel()

        log.debug("source variant has been set. Querying list of drivers.")
        self._list_drivers_task = asyncio.create_task(self._list_drivers())

    @with_context()
    async def _list_drivers(self, context):
        with context.child("wait_apt"):
            await self._wait_apt.wait()
        # The APT_CONFIGURED event (which unblocks _wait_apt.wait) is sent
        # after the user confirms the destruction changes. At this point, the
        # source is already mounted so the user can't go back all the way to
        # the source screen to enable/disable the "search drivers" checkbox.
        if not self.app.controllers.Source.model.search_drivers:
            self.drivers = []
            self.list_drivers_done_event.set()
            return
        apt = self.app.controllers.Mirror.final_apt_configurer
        try:
            async with apt.overlay() as d:
                try:
                    # Make sure ubuntu-drivers is available.
                    await self.ubuntu_drivers.ensure_cmd_exists(d.mountpoint)
                except CommandNotFoundError:
                    self.drivers = []
                else:
                    self.drivers = await self.ubuntu_drivers.list_drivers(
                        root_dir=d.mountpoint, context=context
                    )
        except OverlayCleanupError:
            log.exception("Failed to cleanup overlay. Continuing anyway.")
        self.list_drivers_done_event.set()
        log.debug("Available drivers to install: %s", self.drivers)

    async def GET(self, wait: bool = False) -> DriversResponse:
        local_only = not self.app.base_model.network.has_network
        if wait:
            await self.list_drivers_done_event.wait()

        search_drivers = self.app.controllers.Source.model.search_drivers

        return DriversResponse(
            install=self.model.do_install,
            drivers=self.drivers,
            local_only=local_only,
            search_drivers=search_drivers,
        )

    async def POST(self, data: DriversPayload) -> None:
        self.model.do_install = data.install
        await self.configured()
