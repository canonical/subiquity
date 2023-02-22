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
from socket import gethostname
from subiquitycore.utils import arun_command
from subiquity.server.curtin import run_curtin_command
from subiquity.common.types import (
    ADConnectionInfo,
    AdJoinResult,
)

log = logging.getLogger('subiquity.server.ad_joiner')


class AdJoinStrategy():
    realm = "/usr/sbin/realm"
    pam = "/usr/sbin/pam-auth-update"

    def __init__(self, app):
        self.app = app

    async def do_join(self, info: ADConnectionInfo, hostname: str, context) \
            -> AdJoinResult:
        """ This method changes the hostname and perform a real AD join, thus
            should only run in a live session. """
        result = AdJoinResult.JOIN_ERROR
        hostname_current = gethostname()
        # Set hostname for AD to determine FQDN (no FQDN option in realm join,
        # only adcli, which only understands the live system, but not chroot)
        cp = await arun_command(['hostname', hostname])
        if cp.returncode:
            log.info("Failed to set live session hostname for adcli")
            return result

        root_dir = self.app.root
        cp = await run_curtin_command(
            self.app, context, "in-target", "-t", root_dir,
            "--", self.realm, "join", "--install", root_dir, "--user",
            info.admin_name, "--computer-name", hostname, "--unattended",
            info.domain_name, private_mounts=True, input=info.password,
            timeout=60)

        if not cp.returncode:
            # Restoring the live session hostname.
            # Enable pam_mkhomedir
            cp = await run_curtin_command(self.app, context, "in-target",
                                          "-t", root_dir, "--",
                                          self.pam, "--package",
                                          "--enable", "mkhomedir",
                                          private_mounts=True)

            if cp.returncode:
                result = AdJoinResult.PAM_ERROR
            else:
                result = AdJoinResult.OK

        cp = await arun_command(['hostname', hostname_current])
        if cp.returncode:
            log.info("Failed to restore live session hostname")

        return result


class StubStrategy(AdJoinStrategy):
    async def do_join(self, info: ADConnectionInfo, hostname: str, context) \
            -> AdJoinResult:
        """ Enables testing without real join. The result depends on the
            domain name initial character, such that if it is:
            - p or P: returns PAM_ERROR.
            - j or J: returns JOIN_ERROR.
            - returns OK otherwise. """
        initial = info.domain_name[0]
        if initial in ('j', 'J'):
            return AdJoinResult.JOIN_ERROR

        if initial in ('p', 'P'):
            return AdJoinResult.PAM_ERROR

        return AdJoinResult.OK


class AdJoiner():
    def __init__(self, app):
        self._result = AdJoinResult.UNKNOWN
        self._completion_event = asyncio.Event()
        if app.opts.dry_run:
            self.strategy = StubStrategy(app)
        else:
            self.strategy = AdJoinStrategy(app)

    async def join_domain(self, info: ADConnectionInfo, hostname: str,
                          context) -> AdJoinResult:
        if hostname:
            self._result = await self.strategy.do_join(info, hostname, context)
        else:
            self._result = AdJoinResult.EMPTY_HOSTNAME

        self._completion_event.set()
        return self._result

    async def join_result(self):
        await self._completion_event.wait()
        return self._result
