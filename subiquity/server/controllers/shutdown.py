# Copyright 2020 Canonical, Ltd.
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
import os
import platform
import subprocess

from subiquity.common.apidef import API
from subiquity.common.types import ShutdownMode
from subiquity.server.controller import SubiquityController
from subiquity.server.controllers.install import ApplicationState
from subiquity.server.types import InstallerChannels
from subiquitycore.async_helpers import run_bg_task
from subiquitycore.context import with_context
from subiquitycore.file_util import open_perms, set_log_perms
from subiquitycore.utils import run_command

log = logging.getLogger("subiquity.server.controllers.shutdown")


class ShutdownController(SubiquityController):
    endpoint = API.shutdown
    autoinstall_key = "shutdown"
    autoinstall_schema = {"type": "string", "enum": ["reboot", "poweroff"]}

    def __init__(self, app):
        super().__init__(app)
        # user_shutdown_event is set when the user requests the shutdown.
        # server_reboot_event is set when the server is ready for shutdown
        # shuttingdown_event is set when the shutdown has begun (so don't
        # depend on anything actually happening after it is set, it's all a bag
        # of races from that point!)
        self.user_shutdown_event = asyncio.Event()
        self.server_reboot_event = asyncio.Event()
        self.shuttingdown_event = asyncio.Event()
        self.mode = ShutdownMode.REBOOT

    def load_autoinstall_data(self, data):
        if data == "reboot":
            self.mode = ShutdownMode.REBOOT
        elif data == "poweroff":
            self.mode = ShutdownMode.POWEROFF

    async def POST(self, mode: ShutdownMode, immediate: bool = False):
        self.mode = mode
        self.app.controllers.Install.stop_uu()
        self.user_shutdown_event.set()
        if immediate:
            self.server_reboot_event.set()
        await self.shuttingdown_event.wait()

    def interactive(self):
        return self.app.interactive

    def start(self):
        run_bg_task(self._wait_install())
        run_bg_task(self._run())

    async def _wait_install(self):
        await self.app.controllers.Install.install_task
        await self.app.controllers.Late.run_event.wait()
        await self.copy_logs_to_target()
        self.server_reboot_event.set()

    async def _run(self):
        await self.server_reboot_event.wait()
        if self.app.interactive:
            await self.user_shutdown_event.wait()
            await self.shutdown()
        elif self.app.state == ApplicationState.DONE:
            await self.shutdown()

    @with_context()
    async def copy_logs_to_target(self, context):
        if self.opts.dry_run and "copy-logs-fail" in self.app.debug_flags:
            raise PermissionError()
        if self.app.controllers.Filesystem.reset_partition_only:
            return
        if self.app.base_model.source.current.variant == "core":
            # Possibly should copy logs somewhere else in this case?
            return
        target_logs = os.path.join(self.app.base_model.target, "var/log/installer")
        if self.opts.dry_run:
            os.makedirs(target_logs, exist_ok=True)
        else:
            # Preserve ephemeral boot cloud-init logs if applicable
            cloudinit_logs = [
                cloudinit_log
                for cloudinit_log in (
                    "/var/log/cloud-init.log",
                    "/var/log/cloud-init-output.log",
                )
                if os.path.exists(cloudinit_log)
            ]
            if cloudinit_logs:
                await self.app.command_runner.run(
                    ["cp", "-a"] + cloudinit_logs + ["/var/log/installer"]
                )
            await self.app.command_runner.run(
                ["cp", "-aT", "/var/log/installer", target_logs]
            )
            # Close the permissions from group writes on the target.
            set_log_perms(target_logs, isdir=True, group_write=False)

        journal_txt = os.path.join(target_logs, "installer-journal.txt")
        try:
            with open_perms(journal_txt) as output:
                await self.app.command_runner.run(
                    ["journalctl", "-b"], stdout=output, stderr=subprocess.STDOUT
                )
        except Exception:
            log.exception("saving journal failed")

    @with_context(description="mode={self.mode.name}")
    async def shutdown(self, context):
        await self.app.hub.abroadcast(InstallerChannels.PRE_SHUTDOWN)
        # As PRE_SHUTDOWN is supposed to be as close as possible to the
        # shutdown, we probably don't want additional logic in between.
        self.shuttingdown_event.set()
        if self.opts.dry_run:
            self.app.exit()
        else:
            # On shutdown, it seems that the asynchronous command runners are not
            # reliable.  Best to keep using the traditional sort.
            if self.app.state == ApplicationState.DONE:
                if platform.machine() == "s390x":
                    run_command(["chreipl", "/target/boot"])
            if self.mode == ShutdownMode.REBOOT:
                run_command(["/sbin/reboot"])
            elif self.mode == ShutdownMode.POWEROFF:
                run_command(["/sbin/poweroff"])
