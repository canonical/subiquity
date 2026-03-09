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
import pathlib
import subprocess

from subiquity.common.apidef import API
from subiquity.common.types import ShutdownMode
from subiquity.server.controller import SubiquityController
from subiquity.server.controllers.install import ApplicationState
from subiquity.server.shutdown import initiate_poweroff, initiate_reboot
from subiquity.server.types import InstallerChannels
from subiquitycore.async_helpers import run_bg_task
from subiquitycore.context import with_context
from subiquitycore.file_util import open_perms, set_log_perms

log = logging.getLogger("subiquity.server.controllers.shutdown")


async def _run_direct(cmd, **kwargs):
    """Run a command directly (no systemd-run wrapper).

    Used on Windows loopback boot where systemd-run --wait deadlocks
    due to loop device I/O issues.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=subprocess.DEVNULL,
        **kwargs,
    )
    await proc.communicate()


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
        if self._is_windows_loopback_boot():
            # On Windows loopback boot, copy_logs_to_target() hangs because
            # command_runner wraps every command in systemd-run --wait, which
            # deadlocks due to loop device I/O issues.  Use direct subprocess
            # calls instead so the logs still get copied, then let the normal
            # shutdown path proceed to _pre_shutdown() which does sysrq-b.
            log.debug("Windows loopback boot: copying logs without "
                       "systemd-run")
            await self._copy_logs_to_target_direct()
        else:
            await self.copy_logs_to_target()
        self.server_reboot_event.set()

    @staticmethod
    def _is_windows_loopback_boot():
        """Check if we booted via the Windows installer's GRUB loopback."""
        try:
            cmdline = pathlib.Path("/proc/cmdline").read_text()
            return "akash.from-windows" in cmdline
        except Exception:
            return False

    async def _copy_logs_to_target_direct(self):
        """Copy installer logs to /target without systemd-run.

        On Windows loopback boot the normal copy_logs_to_target() deadlocks
        because command_runner wraps commands in systemd-run --wait.  This
        method runs the same cp/rsync/journalctl commands directly via
        subprocess with timeouts so the logs are preserved and the shutdown
        pipeline can proceed to _pre_shutdown() (which triggers sysrq-b).
        """
        if self.app.controllers.Filesystem.reset_partition_only:
            return
        target_logs = os.path.join(
            self.app.base_model.target, "var/log/installer")
        try:
            os.makedirs(target_logs, exist_ok=True)
        except Exception:
            log.exception("failed to create target log dir")
            return

        # Copy cloud-init logs
        for logfile in ("/var/log/cloud-init.log",
                        "/var/log/cloud-init-output.log"):
            if os.path.exists(logfile):
                try:
                    set_log_perms(logfile)
                    await asyncio.wait_for(
                        _run_direct(["cp", "-a", logfile,
                                     "/var/log/installer"]),
                        timeout=30)
                except Exception:
                    log.debug("direct cp %s failed", logfile)

        # rsync installer logs
        try:
            await asyncio.wait_for(
                _run_direct(["rsync", "-a", "/var/log/installer/",
                             target_logs]),
                timeout=60)
            set_log_perms(target_logs, mode=0o770, group="adm")
        except Exception:
            log.debug("direct rsync to target failed")

        # Save journal
        journal_txt = os.path.join(target_logs, "installer-journal.txt")
        try:
            with open_perms(journal_txt) as output:
                await asyncio.wait_for(
                    _run_direct(["journalctl", "-b"],
                                stdout=output,
                                stderr=subprocess.STDOUT),
                    timeout=30)
        except Exception:
            log.debug("direct journalctl save failed")

    async def _run(self):
        await self.server_reboot_event.wait()
        if self.app.interactive:
            await self.user_shutdown_event.wait()
            await self.shutdown()
        elif self.app.state == ApplicationState.DONE:
            await self.shutdown()

    async def copy_cloud_init_logs(self, target_logs):
        # Preserve ephemeral boot cloud-init logs if applicable
        cloudinit_logs = (
            "/var/log/cloud-init.log",
            "/var/log/cloud-init-output.log",
        )
        for logfile in cloudinit_logs:
            if not os.path.exists(logfile):
                continue
            set_log_perms(logfile)
            await self.app.command_runner.run(
                ["cp", "-a", logfile, "/var/log/installer"]
            )

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
            await self.copy_cloud_init_logs(target_logs)
            await self.app.command_runner.run(
                ["rsync", "-a", "/var/log/installer/", target_logs]
            )
            # explicitly setting the expected permissions on this dir
            set_log_perms(target_logs, mode=0o770, group="adm")

        journal_txt = os.path.join(target_logs, "installer-journal.txt")
        try:
            with open_perms(journal_txt) as output:
                await self.app.command_runner.run(
                    ["journalctl", "-b"],
                    capture=True,
                    stdout=output,
                    stderr=subprocess.STDOUT,
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
            if self.mode == ShutdownMode.REBOOT:
                await initiate_reboot()
            elif self.mode == ShutdownMode.POWEROFF:
                await initiate_poweroff()
