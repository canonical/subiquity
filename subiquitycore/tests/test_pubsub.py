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

from unittest.mock import MagicMock

from subiquitycore.tests import SubiTestCase
from subiquitycore.pubsub import MessageHub
from subiquitycore.tests.util import run_coro


class TestMessageHub(SubiTestCase):
    def setUp(self):
        self.hub = MessageHub()

    def test_multicall(self):
        cb = MagicMock()
        expected_calls = 3
        channel_id = 1234
        for _ in range(expected_calls):
            self.hub.subscribe(channel_id, cb)
        run_coro(self.hub.abroadcast(channel_id))
        self.assertEqual(expected_calls, cb.call_count)

    def test_multisubscriber(self):
        cbs = [MagicMock() for _ in range(4)]
        channel_id = 2345
        for cb in cbs:
            self.hub.subscribe(channel_id, cb)
        run_coro(self.hub.abroadcast(channel_id))
        for cb in cbs:
            cb.assert_called_once_with()

    def test_message_arg(self):
        cb = MagicMock()
        channel_id = 'test-message-arg'
        self.hub.subscribe(channel_id, cb)
        run_coro(self.hub.abroadcast(channel_id, '0', 1, 'two', [3], four=4))
        cb.assert_called_once_with('0', 1, 'two', [3], four=4)
