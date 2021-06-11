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

from subiquitycore.tests import SubiTestCase
from subiquitycore.pubsub import EventCallback
from subiquitycore.tests.util import run_coro


async def wait_other_tasks():
    if hasattr(asyncio, 'all_tasks'):
        tasks = asyncio.all_tasks()  # py 3.7+
    else:
        tasks = asyncio.Task.all_tasks()  # py 3.6
    tasks.remove(asyncio.current_task())
    await asyncio.wait(tasks)


class TestEventCallback(SubiTestCase):
    def test_basic(self):
        def job():
            self.thething.broadcast(42)

        def cb(val, mydata):
            self.assertEqual(42, val)
            self.assertEqual('bacon', mydata)
            self.called += 1

        async def fn():
            self.called = 0
            self.thething = EventCallback()
            calls_expected = 3
            for _ in range(calls_expected):
                self.thething.subscribe(cb, 'bacon')
            job()
            await wait_other_tasks()
            self.assertEqual(calls_expected, self.called)

        run_coro(fn())
