# Copyright 2019 Canonical, Ltd.
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
import os

from systemd import journal

from subiquitycore.context import with_context
from subiquitycore.utils import arun_command

from subiquity.common.types import InstallState
from subiquity.server.controller import NonInteractiveController


class CmdListController(NonInteractiveController):

    autoinstall_default = []
    autoinstall_schema = {
        'type': 'array',
        'items': {
            'type': ['string', 'array'],
            'items': {'type': 'string'},
            },
        }
    cmds = ()
    cmd_check = True
    send_to_journal = False

    def __init__(self, app):
        super().__init__(app)
        self.run_event = asyncio.Event()

    def load_autoinstall_data(self, data):
        self.cmds = data

    def env(self):
        return os.environ.copy()

    @with_context()
    async def run(self, context):
        env = self.env()
        for i, cmd in enumerate(self.cmds):
            if isinstance(cmd, str):
                desc = cmd
            else:
                desc = ' '.join(cmd)
            with context.child("command_{}".format(i), desc):
                if isinstance(cmd, str):
                    cmd = ['sh', '-c', cmd]
                if self.send_to_journal:
                    journal.send(
                        "  running " + desc,
                        SYSLOG_IDENTIFIER=self.app.early_commands_syslog_id)
                    cmd = [
                        'systemd-cat', '--level-prefix=false',
                        '--identifier=' + self.app.early_commands_syslog_id,
                        ] + cmd
                await arun_command(
                    cmd, env=env,
                    stdin=None, stdout=None, stderr=None,
                    check=self.cmd_check)
        self.run_event.set()


class EarlyController(CmdListController):

    autoinstall_key = 'early-commands'
    send_to_journal = True


class LateController(CmdListController):

    autoinstall_key = 'late-commands'

    def env(self):
        env = super().env()
        env['TARGET_MOUNT_POINT'] = self.app.base_model.target
        return env

    def start(self):
        self.app.aio_loop.create_task(self._run())

    async def _run(self):
        Install = self.app.controllers.Install
        await Install.install_task
        if Install.install_state == InstallState.DONE:
            await self.run()


class ErrorController(CmdListController):

    autoinstall_key = 'error-commands'
    cmd_check = False
