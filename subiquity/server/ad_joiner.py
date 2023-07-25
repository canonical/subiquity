# Copyright 2023 Canonical, Ltd.
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
from contextlib import contextmanager
from socket import gethostname
from subprocess import CalledProcessError

from subiquity.common.types import AdConnectionInfo, AdJoinResult
from subiquity.server.curtin import run_curtin_command
from subiquitycore.utils import arun_command, run_command

log = logging.getLogger("subiquity.server.ad_joiner")


@contextmanager
def joining_context(hostname: str, root_dir: str):
    """Temporarily adjusts the host name to [hostname] and bind-mounts
    interesting system directories in preparation for running realm
    in target's [root_dir], undoing it all on exit."""
    hostname_current = gethostname()
    binds = ("/proc", "/sys", "/dev", "/run")
    try:
        hostname_process = run_command(["hostname", hostname])
        for bind in binds:
            bound_dir = os.path.join(root_dir, bind[1:])
            if bound_dir != bind:
                run_command(["mount", "--bind", bind, bound_dir])
        yield hostname_process
    finally:
        # Restoring the live session hostname.
        hostname_process = run_command(["hostname", hostname_current])
        if hostname_process.returncode:
            log.info("Failed to restore live session hostname")
        for bind in reversed(binds):
            bound_dir = os.path.join(root_dir, bind[1:])
            if bound_dir != bind:
                run_command(["umount", "-f", bound_dir])


class AdJoinStrategy:
    realm = "/usr/sbin/realm"
    pam = "/usr/sbin/pam-auth-update"

    def __init__(self, app):
        self.app = app

    async def do_join(
        self, info: AdConnectionInfo, hostname: str, context
    ) -> AdJoinResult:
        """This method changes the hostname and perform a real AD join, thus
        should only run in a live session."""
        root_dir = self.app.base_model.target
        # Set hostname for AD to determine FQDN (no FQDN option in realm join,
        # only adcli, which only understands the live system, but not chroot)
        with joining_context(hostname, root_dir) as host_process:
            if host_process.returncode:
                log.info("Failed to set live session hostname for adcli")
                return AdJoinResult.JOIN_ERROR

            cp = await arun_command(
                [
                    self.realm,
                    "join",
                    "--install",
                    root_dir,
                    "--user",
                    info.admin_name,
                    "--computer-name",
                    hostname,
                    "--unattended",
                    info.domain_name,
                ],
                input=info.password,
            )

            if cp.returncode:
                # Try again without the computer name. Lab tests shown more
                # success in this setup, but I'm still not sure if we should
                # drop the computer name attempt, since that's the way Ubiquity
                # has been doing for ages.
                log.debug("Joining operation failed:")
                log.debug(cp.stderr)
                log.debug(cp.stdout)
                log.debug("Trying again without overriding the computer name:")
                cp = await arun_command(
                    [
                        self.realm,
                        "join",
                        "--install",
                        root_dir,
                        "--user",
                        info.admin_name,
                        "--unattended",
                        info.domain_name,
                    ],
                    input=info.password,
                )

                if cp.returncode:
                    log.debug("Joining operation failed:")
                    log.debug(cp.stderr)
                    log.debug(cp.stdout)
                    return AdJoinResult.JOIN_ERROR

            # Enable pam_mkhomedir
            try:
                # The function raises if the process fail.
                await run_curtin_command(
                    self.app,
                    context,
                    "in-target",
                    "-t",
                    root_dir,
                    "--",
                    self.pam,
                    "--package",
                    "--enable",
                    "mkhomedir",
                    private_mounts=False,
                )

                return AdJoinResult.OK
            except CalledProcessError:
                # The app command runner doesn't give us output in case of
                # failure in the wait() method, which is called by
                # run_curtin_command
                log.info("Failed to update pam-auth")
                return AdJoinResult.PAM_ERROR

        return AdJoinResult.JOIN_ERROR


class StubStrategy(AdJoinStrategy):
    async def do_join(
        self, info: AdConnectionInfo, hostname: str, context
    ) -> AdJoinResult:
        """Enables testing without real join. The result depends on the
        domain name initial character, such that if it is:
        - p or P: returns PAM_ERROR.
        - j or J: returns JOIN_ERROR.
        - returns OK otherwise."""
        initial = info.domain_name[0]
        if initial in ("j", "J"):
            return AdJoinResult.JOIN_ERROR

        if initial in ("p", "P"):
            return AdJoinResult.PAM_ERROR

        return AdJoinResult.OK


class AdJoiner:
    def __init__(self, app):
        self._result = AdJoinResult.UNKNOWN
        self._completion_event = asyncio.Event()
        if app.opts.dry_run:
            self.strategy = StubStrategy(app)
        else:
            self.strategy = AdJoinStrategy(app)

    async def join_domain(
        self, info: AdConnectionInfo, hostname: str, context
    ) -> AdJoinResult:
        if hostname:
            self._result = await self.strategy.do_join(info, hostname, context)
        else:
            self._result = AdJoinResult.EMPTY_HOSTNAME

        self._completion_event.set()
        return self._result

    async def join_result(self):
        await self._completion_event.wait()
        return self._result
