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

import os

from subiquitycore.context import with_context
from subiquitycore.utils import arun_command

from subiquity.controller import SubiquityController


class CmdListController(SubiquityController):

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

    def load_autoinstall_data(self, data):
        self.cmds = data

    def env(self):
        return os.environ.copy()

    @with_context()
    async def run(self, context):
        env = self.env()
        for i, cmd in enumerate(self.cmds):
            with context.child("command_{}".format(i), cmd):
                if isinstance(cmd, str):
                    cmd = ['sh', '-c', cmd]
                await arun_command(
                    cmd, env=env,
                    stdin=None, stdout=None, stderr=None,
                    check=self.cmd_check)


class EarlyController(CmdListController):

    autoinstall_key = 'early-commands'


class LateController(CmdListController):

    autoinstall_key = 'late-commands'

    def env(self):
        env = super().env()
        env['TARGET_MOUNT_POINT'] = self.app.base_model.target
        return env

    @with_context()
    async def apply_autoinstall_config(self, context):
        await self.run(context=context)
