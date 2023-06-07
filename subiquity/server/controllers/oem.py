# Copyright 2023 Canonical, Ltd.
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

from subiquity.server.apt import OverlayCleanupError
from subiquity.server.controller import SubiquityController
from subiquity.server.types import InstallerChannels
from subiquity.server.ubuntu_drivers import (
    CommandNotFoundError,
    get_ubuntu_drivers_interface,
    )

log = logging.getLogger('subiquity.server.controllers.oem')


class OEMController(SubiquityController):

    model_name = "oem"

    def __init__(self, app) -> None:
        super().__init__(app)
        # At this point, the source variant has not been selected but it only
        # has an impact if we're listing drivers, not OEM metapackages.
        self.ubuntu_drivers = get_ubuntu_drivers_interface(self.app)

        self.load_metapkgs_task: Optional[asyncio.Task] = None

    def start(self) -> None:
        self._wait_apt = asyncio.Event()
        self.app.hub.subscribe(
            InstallerChannels.APT_CONFIGURED,
            self._wait_apt.set)

        async def list_and_mark_configured() -> None:
            await self.load_metapackages_list()
            await self.configured()

        self.load_metapkgs_task = asyncio.create_task(
                list_and_mark_configured())

    @with_context()
    async def load_metapackages_list(self, context) -> None:
        with context.child("wait_apt"):
            await self._wait_apt.wait()
        apt = self.app.controllers.Mirror.final_apt_configurer
        try:
            async with apt.overlay() as d:
                try:
                    # Make sure ubuntu-drivers is available.
                    await self.ubuntu_drivers.ensure_cmd_exists(d.mountpoint)
                except CommandNotFoundError:
                    self.model.metapkgs = []
                else:
                    self.model.metapkgs = await self.ubuntu_drivers.list_oem(
                        root_dir=d.mountpoint,
                        context=context)
        except OverlayCleanupError:
            log.exception("Failed to cleanup overlay. Continuing anyway.")
        log.debug("OEM meta-packages to install: %s", self.model.metapkgs)
