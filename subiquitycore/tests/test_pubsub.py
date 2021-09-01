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
from subiquitycore.pubsub import (MessageHub, EventCallback)
from subiquitycore.tests.util import run_coro


class TestMessageHub(SubiTestCase):
    def test_basic(self):
        def cb(mydata):
            self.assertEqual(private_data, mydata)
            self.called += 1

        async def fn():
            calls_expected = 3
            for _ in range(calls_expected):
                self.hub.subscribe(channel_id, cb, private_data)
            await self.hub.broadcast(channel_id)
            self.assertEqual(calls_expected, self.called)

        self.called = 0
        channel_id = 1234
        private_data = 42
        self.hub = MessageHub()
        run_coro(fn())


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
            await self.thething.broadcast(42)
            self.assertEqual(calls_expected, self.called)

        run_coro(fn())
