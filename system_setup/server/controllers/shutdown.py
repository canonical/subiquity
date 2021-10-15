# Copyright 2020-2021 Canonical, Ltd.
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

import enum
import os
import logging

from subiquitycore.context import with_context
from subiquity.common.types import ShutdownMode
from subiquity.server.controllers import ShutdownController

log = logging.getLogger("system_setup.server.controllers.restart")


class WSLShutdownMode(enum.Enum):
    COMPLETE = -1


class SetupShutdownController(ShutdownController):

    def __init__(self, app):
        # This isn't the most beautiful way, but the shutdown controller
        # depends on Install, override with our configure one.
        super().__init__(app)
        self.root_dir = app.base_model.root
        self.app.controllers.Install = self.app.controllers.Configure
        self.mode = WSLShutdownMode.COMPLETE  # allow the complete mode

    def start(self):
        self.app.aio_loop.create_task(self._wait_install())
        self.app.aio_loop.create_task(self._run())

    async def _wait_install(self):
        await self.app.controllers.Install.install_task
        await self.app.controllers.Late.run_event.wait()
        self.server_reboot_event.set()

    @with_context(description='mode={self.mode.name}')
    def shutdown(self, context):
        self.shuttingdown_event.set()
        launcher_status = "complete"

        if self.mode == ShutdownMode.REBOOT:
            log.debug("rebooting")
            launcher_status = "reboot"
        elif self.mode == ShutdownMode.POWEROFF:
            log.debug("Shutting down")
            launcher_status = "shutdown"

        subiquity_rundir = os.path.join(self.root_dir, "run", "subiquity")
        os.makedirs(subiquity_rundir, exist_ok=True)
        lau_status_file = os.path.join(subiquity_rundir, "launcher-status")
        with open(lau_status_file, "w+") as f:
            f.write(launcher_status)
        self.app.exit()
