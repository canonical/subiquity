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
import os
import random
import subprocess
from contextlib import suppress
from typing import List, Literal, Optional

from subiquitycore.utils import astart_command


def _dollar_escape(s: str) -> str:
    """Return the string passed as a parameter with dollar signs escaped
    for systemd-run."""
    return s.replace("$", "$$")


class LoggedCommandRunner:
    """Class that executes commands using systemd-run."""

    def __init__(self, ident, *, use_systemd_user: Optional[bool] = None) -> None:
        self.ident = ident
        self.env_allowlist = [
            "PATH",
            "PYTHONPATH",
            "PYTHON",
            "TARGET_MOUNT_POINT",
            "SNAP",
            "SUBIQUITY_REPLAY_TIMESCALE",
        ]
        if use_systemd_user is not None:
            self.use_systemd_user = use_systemd_user
        else:
            self.use_systemd_user = os.geteuid() != 0

    def _forge_systemd_cmd(
        self,
        cmd: List[str],
        private_mounts: bool,
        capture: bool,
        stdin: Literal[subprocess.PIPE, subprocess.DEVNULL],
    ) -> List[str]:
        """Return the supplied command prefixed with the systemd-run stuff."""
        prefix = [
            "systemd-run",
            "--wait",
            "--same-dir",
            "--property",
            f"SyslogIdentifier={self.ident}",
        ]
        if private_mounts:
            prefix.extend(("--property", "PrivateMounts=yes"))
        if self.use_systemd_user:
            prefix.append("--user")
        if stdin == subprocess.PIPE or capture:
            if stdin == subprocess.PIPE and not capture:
                raise ValueError("cannot pipe stdin but not stdout/stderr")
            prefix.append("--pipe")
        for key in self.env_allowlist:
            with suppress(KeyError):
                prefix.extend(("--setenv", f"{key}={os.environ[key]}"))

        prefix.append("--")

        return prefix + [_dollar_escape(arg) for arg in cmd]

    async def start(
        self,
        cmd: List[str],
        *,
        private_mounts: bool = False,
        capture: bool = False,
        stdin: Literal[subprocess.PIPE, subprocess.DEVNULL] = subprocess.DEVNULL,
        **astart_kwargs,
    ) -> asyncio.subprocess.Process:
        forged: List[str] = self._forge_systemd_cmd(
            cmd,
            private_mounts=private_mounts,
            capture=capture,
            stdin=stdin,
        )

        proc = await astart_command(forged, stdin=stdin, **astart_kwargs)

        proc.args = forged

        return proc

    async def wait(
        self,
        proc: asyncio.subprocess.Process,
        input: Optional[bytes] = None,
    ) -> subprocess.CompletedProcess:
        stdout, stderr = await proc.communicate(input=input)
        # .communicate() forces returncode to be set to a value
        assert proc.returncode is not None
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, proc.args, output=stdout, stderr=stderr
            )
        else:
            return subprocess.CompletedProcess(
                proc.args, proc.returncode, stdout=stdout, stderr=stderr
            )

    async def run(
        self, cmd: List[str], input: Optional[bytes] = None, **opts
    ) -> subprocess.CompletedProcess:
        stdin = subprocess.PIPE if input is not None else subprocess.DEVNULL
        proc = await self.start(cmd, stdin=stdin, **opts)
        return await self.wait(proc, input=input)


class DryRunCommandRunner(LoggedCommandRunner):
    def __init__(self, *args, delay, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.delay = delay

    def _forge_systemd_cmd(
        self,
        cmd: List[str],
        private_mounts: bool,
        capture: bool,
        stdin: Literal[subprocess.PIPE, subprocess.DEVNULL],
    ) -> List[str]:
        if "scripts/replay-curtin-log.py" in cmd:
            # We actually want to run this command
            prefixed_command = cmd
        else:
            prefixed_command = [
                "scripts/sleep-then-execute.sh",
                str(self._get_delay_for_cmd(cmd)),
                "echo",
                "not running:",
            ] + cmd

        return super()._forge_systemd_cmd(
            prefixed_command,
            private_mounts=private_mounts,
            capture=capture,
            stdin=stdin,
        )

    def _get_delay_for_cmd(self, cmd: List[str]) -> float:
        if "scripts/replay-curtin-log.py" in cmd:
            return 0
        elif "unattended-upgrades" in cmd:
            return 3 * self.delay
        elif "chzdev" in cmd:
            return 0.4 * random.random() * self.delay
        else:
            return self.delay

    async def start(
        self,
        cmd: List[str],
        *,
        private_mounts: bool = False,
        capture: bool = False,
        **astart_kwargs,
    ) -> asyncio.subprocess.Process:
        proc = await super().start(
            cmd, private_mounts=private_mounts, capture=capture, **astart_kwargs
        )
        return proc


def get_command_runner(app):
    if app.opts.dry_run:
        return DryRunCommandRunner(app.log_syslog_id, delay=2 / app.scale_factor)
    else:
        return LoggedCommandRunner(app.log_syslog_id)
