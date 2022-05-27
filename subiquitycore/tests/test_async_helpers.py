# Copyright 2022 Canonical, Ltd.
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
import unittest
from unittest.mock import AsyncMock

from parameterized import parameterized

from subiquitycore.async_helpers import (
    SingleInstanceTask,
    TaskAlreadyRunningError,
)


class TestSingleInstanceTask(unittest.IsolatedAsyncioTestCase):
    @parameterized.expand([(True, 2), (False, 1)])
    async def test_cancellable(self, cancel_restart, expected_call_count):
        async def fn():
            await asyncio.sleep(3)
            raise Exception('timeout')

        mock_fn = AsyncMock(side_effect=fn)
        sit = SingleInstanceTask(mock_fn, cancel_restart=cancel_restart)
        await sit.start()
        await asyncio.sleep(.01)
        try:
            await sit.start()
        except TaskAlreadyRunningError:
            restarted = False
        else:
            restarted = True
        sit.task.cancel()
        self.assertEqual(expected_call_count, mock_fn.call_count)
        self.assertEqual(cancel_restart, restarted)
