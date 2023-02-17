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
from subiquity.common.types import (
    ADConnectionInfo,
    AdJoinResult,
)


class AdJoinStrategy():
    cmd = "/usr/sbin/realm"
    args = ["join"]

    async def do_join(self, info: ADConnectionInfo) -> AdJoinResult:
        # Now what?
        # TODO: Join.
        result = AdJoinResult.JOIN_ERROR
        return await asyncio.sleep(3, result=result)


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
    def __init__(self, dry_run: bool):
        self._result = AdJoinResult.UNKNOWN
        self.join_task = None
        if dry_run:
            self.strategy = StubStrategy()
        else:
            self.strategy = AdJoinStrategy()

    async def join_domain(self, info: ADConnectionInfo) -> AdJoinResult:
        self.join_task = asyncio.create_task(self.async_join(info))
        self._result = await self.join_task
        return self._result

    async def async_join(self, info: ADConnectionInfo) -> AdJoinResult:
        return await self.strategy.do_join(info)

    async def join_result(self):
        if self.join_task is None:
            return AdJoinResult.UNKNOWN

        return await self.join_task
