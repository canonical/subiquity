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

import logging

from subiquitycore.context import with_context
from subiquity.common.types import ShutdownMode
from subiquity.server.controllers import ShutdownController

log = logging.getLogger("system_setup.server.controllers.restart")


class SetupShutdownController(ShutdownController):

    def __init__(self, app):
        # This isn't the most beautiful way, but the shutdown controller
        # depends on Install, override with our configure one.
        super().__init__(app)
        self.app.controllers.Install = self.app.controllers.Configure

    def start(self):
        # Do not copy logs to target
        self.server_reboot_event.set()
        self.app.aio_loop.create_task(self._run())

    @with_context(description='mode={self.mode.name}')
    def shutdown(self, context):
        self.shuttingdown_event.set()
        if not self.opts.dry_run:
            if self.mode == ShutdownMode.REBOOT:
                # TODO WSL:
                # Implement a reboot that doesn't depend on systemd
                log.Warning("reboot command not implemented")
            elif self.mode == ShutdownMode.POWEROFF:
                # TODO WSL:
                # Implement a poweroff that doesn't depend on systemd
                log.Warning("poweroff command not implemented")
        self.app.exit()
