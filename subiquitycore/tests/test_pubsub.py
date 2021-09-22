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

from subiquitycore.tests import SubiTestCase
from subiquitycore.pubsub import MessageHub
from subiquitycore.tests.util import run_coro


class TestMessageHub(SubiTestCase):
    def test_basic(self):
        def cb(actual_private):
            self.assertEqual(private_data, actual_private)
            nonlocal actual_calls
            actual_calls += 1

        actual_calls = 0
        expected_calls = 3
        channel_id = 1234
        private_data = 42
        hub = MessageHub()
        for _ in range(expected_calls):
            hub.subscribe(channel_id, cb, private_data)
        run_coro(hub.abroadcast(channel_id))
        self.assertEqual(expected_calls, actual_calls)

    def test_message_arg(self):
        def cb(zero, one, two, three, *args):
            self.assertEqual(broadcast_data, zero)
            self.assertEqual(1, one)
            self.assertEqual('two', two)
            self.assertEqual([3], three)
            self.assertEqual(0, len(args))
            nonlocal called
            called = True

        called = False
        channel_id = 'test-message-arg'
        broadcast_data = 'broadcast-data'
        hub = MessageHub()
        hub.subscribe(channel_id, cb, 1, 'two', [3])
        run_coro(hub.abroadcast(channel_id, broadcast_data))
        self.assertTrue(called)
