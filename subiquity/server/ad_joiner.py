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


class AdJoiner():
    def __init__(self):
        self._result = AdJoinResult.UNKNOWN
        self.join_task = None

    async def join_domain(self, info: ADConnectionInfo) -> AdJoinResult:
        self.join_task = asyncio.create_task(self.async_join(info))
        self._result = await self.join_task
        return self._result

    async def async_join(self, info: ADConnectionInfo) -> AdJoinResult:
        # TODO: Join.
        return await asyncio.sleep(3, result=AdJoinResult.JOIN_ERROR)

    async def join_result(self):
        if self.join_task is None:
            return AdJoinResult.UNKNOWN

        return await self.join_task
