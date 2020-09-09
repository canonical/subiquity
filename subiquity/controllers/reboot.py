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

import logging
import os
import platform
import subprocess

from subiquitycore.async_helpers import schedule_task
from subiquitycore.context import with_context
from subiquitycore.utils import arun_command, run_command

from subiquity.controller import SubiquityTuiController

log = logging.getLogger("subiquity.controllers.restart")


class RebootController(SubiquityTuiController):

    def __init__(self, app):
        super().__init__(app)
        self.context.set('hidden', True)

    def interactive(self):
        return self.app.interactive()

    @with_context()
    async def copy_logs_to_target(self, context):
        if self.opts.dry_run and 'copy-logs-fail' in self.app.debug_flags:
            raise PermissionError()
        target_logs = os.path.join(
            self.app.base_model.target, 'var/log/installer')
        if self.opts.dry_run:
            os.makedirs(target_logs, exist_ok=True)
        else:
            await arun_command(
                ['cp', '-aT', '/var/log/installer', target_logs])
        journal_txt = os.path.join(target_logs, 'installer-journal.txt')
        try:
            with open(journal_txt, 'w') as output:
                await arun_command(
                    ['journalctl', '-b'],
                    stdout=output, stderr=subprocess.STDOUT)
        except Exception:
            log.exception("saving journal failed")

    def reboot(self):
        if self.opts.dry_run:
            self.app.exit()
        else:
            if platform.machine() == 's390x':
                run_command(["chreipl", "/target/boot"])
            run_command(["/sbin/reboot"])

    @with_context()
    async def apply_autoinstall_config(self, context):
        await self.copy_logs_to_target(context=context)
        self.reboot()

    async def _run(self):
        await self.copy_logs_to_target()
        await self.app.controllers.InstallProgress.reboot_clicked.wait()
        self.reboot()

    def start_ui(self):
        schedule_task(self._run())

    def cancel(self):
        pass
