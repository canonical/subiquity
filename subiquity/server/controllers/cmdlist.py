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
import shlex
from typing import List, Sequence, Union

import attr
from systemd import journal

from subiquity.common.types import ApplicationState
from subiquity.server.controller import NonInteractiveController
from subiquitycore.async_helpers import run_bg_task
from subiquitycore.context import with_context
from subiquitycore.utils import arun_command


@attr.s(auto_attribs=True)
class Command:
    """Represents a command, specified either as a list of arguments or as a
    single string."""

    args: Union[str, Sequence[str]]
    check: bool

    def desc(self) -> str:
        """Return a user-friendly representation of the command."""
        if isinstance(self.args, str):
            return self.args
        return shlex.join(self.args)

    def as_args_list(self) -> List[str]:
        """Return the command as a list of arguments."""
        if isinstance(self.args, str):
            return ["sh", "-c", self.args]
        return list(self.args)


class CmdListController(NonInteractiveController):
    autoinstall_default = []
    autoinstall_schema = {
        "type": "array",
        "items": {
            "type": ["string", "array"],
            "items": {"type": "string"},
        },
    }
    builtin_cmds: Sequence[Command] = ()
    cmds: Sequence[Command] = ()
    cmd_check = True
    syslog_id = None

    def __init__(self, app):
        super().__init__(app)
        self.run_event = asyncio.Event()

    def load_autoinstall_data(self, data):
        self.cmds = [Command(args=cmd, check=self.cmd_check) for cmd in data]

    def env(self):
        return os.environ.copy()

    @with_context()
    async def run(self, context):
        env = self.env()
        for i, cmd in enumerate(tuple(self.builtin_cmds) + tuple(self.cmds)):
            desc = cmd.desc()
            with context.child("command_{}".format(i), desc):
                args = cmd.as_args_list()
                if self.syslog_id:
                    journal.send("  running " + desc, SYSLOG_IDENTIFIER=self.syslog_id)
                    args = [
                        "systemd-cat",
                        "--level-prefix=false",
                        "--identifier=" + self.syslog_id,
                    ] + args
                await arun_command(
                    args, env=env, stdin=None, stdout=None, stderr=None, check=cmd.check
                )
        self.run_event.set()


class EarlyController(CmdListController):
    autoinstall_key = "early-commands"

    def __init__(self, app):
        super().__init__(app)
        self.syslog_id = app.echo_syslog_id


class LateController(CmdListController):
    autoinstall_key = "late-commands"

    def __init__(self, app):
        super().__init__(app)
        self.syslog_id = app.log_syslog_id

        try:
            hooks_dir = self.app.opts.postinst_hooks_dir
        except AttributeError:
            # NOTE: system_setup imports this controller ; but does not use the
            # postinst hooks mechanism.
            pass
        else:
            if hooks_dir.is_dir():
                self.builtin_cmds = [
                    Command(
                        args=["run-parts", "--debug", "--", str(hooks_dir)],
                        check=False,
                    ),
                ]

    def env(self):
        env = super().env()
        if self.app.base_model.target is not None:
            env["TARGET_MOUNT_POINT"] = self.app.base_model.target
        return env

    def start(self):
        run_bg_task(self._run())

    async def _run(self):
        Install = self.app.controllers.Install
        await Install.install_task
        if self.app.state == ApplicationState.DONE:
            await self.run()


class ErrorController(CmdListController):
    autoinstall_key = "error-commands"
    cmd_check = False

    @with_context()
    async def run(self, context):
        if self.app.interactive:
            self.syslog_id = self.app.log_syslog_id
        else:
            self.syslog_id = self.app.echo_syslog_id
        await super().run(context=context)
