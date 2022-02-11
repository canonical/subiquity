# Copyright 2021 Canonical, Ltd.
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
from contextlib import suppress
import os
import subprocess
from typing import List

from subiquitycore.utils import astart_command


class LoggedCommandRunner:

    def __init__(self, ident):
        self.ident = ident
        self.env_whitelist = [
            "PATH", "PYTHONPATH",
            "PYTHON",
            "TARGET_MOUNT_POINT",
            "SNAP",
        ]

    def _forge_systemd_cmd(self, cmd: List[str], private_mounts: bool) \
            -> List[str]:
        """ Return the supplied command prefixed with the systemd-run stuff.
        """
        prefix = [
            "systemd-run",
            "--wait", "--same-dir",
            "--property", f"SyslogIdentifier={self.ident}",
        ]
        if private_mounts:
            prefix.extend(("--property", "PrivateMounts=yes"))
        for key in self.env_whitelist:
            with suppress(KeyError):
                prefix.extend(("--setenv", f"{key}={os.environ[key]}"))

        prefix.append("--")

        return prefix + cmd

    async def start(self, cmd, private_mounts: bool = False):
        forged: List[str] = self._forge_systemd_cmd(cmd, private_mounts)
        proc = await astart_command(forged)
        proc.args = forged
        return proc

    async def wait(self, proc):
        await proc.communicate()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, proc.args)
        else:
            return subprocess.CompletedProcess(proc.args, proc.returncode)

    async def run(self, cmd, **opts):
        proc = await self.start(cmd, **opts)
        return await self.wait(proc)


class DryRunCommandRunner(LoggedCommandRunner):

    def __init__(self, ident, delay):
        super().__init__(ident)
        self.delay = delay

    def _forge_systemd_cmd(self, cmd: List[str], private_mounts: bool) \
            -> List[str]:
        # We would like to use systemd-run here but unfortunately it requires
        # root privileges.
        # Using systemd-run --user would be an option but it not available
        # everywhere ; so we fallback to using systemd-cat.
        prefix = [
            "systemd-cat",
            "--level-prefix=false",
            f"--identifier={self.ident}",
            "--",
        ]

        if "scripts/replay-curtin-log.py" in cmd:
            # We actually want to run this command
            return prefix + cmd

        return prefix + ["echo", "not running:"] + cmd

    def _get_delay_for_cmd(self, cmd: List[str]) -> float:
        if 'scripts/replay-curtin-log.py' in cmd:
            return 0
        elif 'unattended-upgrades' in cmd:
            return 3 * self.delay
        else:
            return self.delay

    async def start(self, cmd, private_mounts: bool = False):
        delay = self._get_delay_for_cmd(cmd)
        proc = await super().start(cmd, private_mounts)
        await asyncio.sleep(delay)
        return proc


def get_command_runner(app):
    if app.opts.dry_run:
        return DryRunCommandRunner(
            app.log_syslog_id, 2/app.scale_factor)
    else:
        return LoggedCommandRunner(app.log_syslog_id)
