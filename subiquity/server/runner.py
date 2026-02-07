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


class SystemdRunWrapper:
    def __init__(
        self,
        *,
        ident: str,
        use_systemd_user: bool | None = None,
    ) -> None:
        self.ident = ident
        if use_systemd_user is not None:
            self.use_systemd_user = use_systemd_user
        else:
            self.use_systemd_user = os.geteuid() != 0
        self.env_allowlist = [
            "PATH",
            "PYTHONPATH",
            "PYTHON",
            "TARGET_MOUNT_POINT",
            "SNAP",
            "SUBIQUITY_REPLAY_TIMESCALE",
        ]

    def wrap(
        self,
        cmd: list[str],
        *,
        private_mounts: bool,
        capture: bool,
        stdin: Literal[subprocess.PIPE, subprocess.DEVNULL],
    ) -> list[str]:
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


class SleepAndEchoWrapper:
    def __init__(self, *, delay_multiplier: float) -> None:
        self.delay_multiplier = delay_multiplier

    def _get_delay_for_cmd(self, cmd: list[str]) -> float:
        if "scripts/replay-curtin-log.py" in cmd:
            return 0
        elif "unattended-upgrades" in cmd:
            return 3 * self.delay_multiplier
        elif "chzdev" in cmd:
            return 0.4 * random.random() * self.delay_multiplier
        else:
            return self.delay_multiplier

    def wrap(self, cmd: list[str]) -> list[str]:
        if "scripts/replay-curtin-log.py" in cmd:
            # We actually want to run this command
            return cmd
        else:
            return [
                "scripts/sleep-then-execute.sh",
                str(self._get_delay_for_cmd(cmd)),
                "echo",
                "not running:",
            ] + cmd


class AstartBackend:
    """Backend implementation based on astart_command (which supports binary
    data only)"""

    async def start(
        self,
        cmd: list[str],
        **kwargs,
    ) -> asyncio.subprocess.Process:
        proc = await astart_command(cmd, **kwargs)
        proc.args = cmd
        return proc

    async def wait(
        self,
        proc: asyncio.subprocess.Process,
        *,
        input: bytes | None,
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
        self, cmd: list[str], *, input: bytes | None, **kwargs
    ) -> subprocess.CompletedProcess:
        stdin = subprocess.PIPE if input is not None else subprocess.DEVNULL
        proc = await self.start(cmd, stdin=stdin, **kwargs)
        return await self.wait(proc, input=input)


class CommandRunner:
    def __init__(self, *, backend) -> None:
        self.backend = backend

    async def wait(
        self,
        proc: asyncio.subprocess.Process,
        input: bytes | None,
    ) -> subprocess.CompletedProcess:
        return await self.backend.wait(proc, input=input)


class LoggedCommandRunner(CommandRunner):
    def __init__(self, ident, *, use_systemd_user: Optional[bool] = None) -> None:
        self.systemd_run_wrapper = SystemdRunWrapper(
            ident=ident,
            use_systemd_user=use_systemd_user,
        )
        super().__init__(backend=AstartBackend())

    def wrap_command(self, cmd: list[str], *args, **kwargs) -> list[str]:
        return self.systemd_run_wrapper.wrap(cmd, *args, **kwargs)

    async def start(
        self,
        cmd: List[str],
        *,
        private_mounts: bool = False,
        capture: bool = False,
        stdin: Literal[subprocess.PIPE, subprocess.DEVNULL] = subprocess.DEVNULL,
        **backend_kwargs,
    ) -> asyncio.subprocess.Process:
        wrapped: List[str] = self.wrap_command(
            cmd,
            private_mounts=private_mounts,
            capture=capture,
            stdin=stdin,
        )

        return await self.backend.start(wrapped, stdin=stdin, **backend_kwargs)

    async def run(
        self,
        cmd: List[str],
        input: Optional[bytes] = None,
        private_mounts: bool = False,
        capture: bool = False,
        **backend_kwargs,
    ) -> subprocess.CompletedProcess:
        stdin = subprocess.PIPE if input is not None else subprocess.DEVNULL
        wrapped = self.wrap_command(
            cmd, private_mounts=private_mounts, capture=capture, stdin=stdin
        )
        return await self.backend.run(wrapped, input=input, **backend_kwargs)


class DryRunCommandRunner(LoggedCommandRunner):
    def __init__(self, *args, delay, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.sleep_and_echo_wrapper = SleepAndEchoWrapper(delay_multiplier=delay)

    def wrap_command(self, cmd: list[str], *args, **kwargs) -> list[str]:
        return super().wrap_command(
            self.sleep_and_echo_wrapper.wrap(cmd), *args, **kwargs
        )


def get_command_runner(app):
    if app.opts.dry_run:
        return DryRunCommandRunner(app.log_syslog_id, delay=2 / app.scale_factor)
    else:
        return LoggedCommandRunner(app.log_syslog_id)
