# Copyright 2025 Canonical, Ltd.
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

import unittest
from unittest.mock import AsyncMock, Mock, patch

from subiquity.server.controllers.zdev import ZdevAction, ZdevController
from subiquitycore.tests.mocks import make_app


class TestZdevController(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ctrler = ZdevController(make_app())

    def test_make_autoinstall_no_dupes(self):
        self.ctrler.done_ai_actions = [
            ZdevAction(id="0.0.1507", enable=True),
            ZdevAction(id="0.0.1508", enable=False),
            ZdevAction(id="0.0.1509", enable=True),
        ]

        expected = [
            {"id": "0.0.1507", "enabled": True},
            {"id": "0.0.1508", "enabled": False},
            {"id": "0.0.1509", "enabled": True},
        ]
        self.assertEqual(expected, self.ctrler.make_autoinstall())

    def test_make_autoinstall_with_dupes(self):
        action1 = ZdevAction(id="0.0.1507", enable=True)
        action2 = ZdevAction(id="0.0.1508", enable=True)
        self.ctrler.done_ai_actions = [action1, action1, action1, action2, action2]

        expected = [
            {"id": "0.0.1507", "enabled": True},
            {"id": "0.0.1508", "enabled": True},
        ]
        self.assertEqual(expected, self.ctrler.make_autoinstall())

    def test_make_autoinstall_disable_then_enable(self):
        enable = ZdevAction(id="0.0.1507", enable=True)
        disable = ZdevAction(id="0.0.1507", enable=False)
        self.ctrler.done_ai_actions = [disable, enable, disable, disable, enable]

        expected = [
            {"id": "0.0.1507", "enabled": False},
            {"id": "0.0.1507", "enabled": True},
            {"id": "0.0.1507", "enabled": False},
            {"id": "0.0.1507", "enabled": True},
        ]
        self.assertEqual(expected, self.ctrler.make_autoinstall())

    async def test_handle_zdevs__none(self):
        self.ctrler.load_autoinstall_data([])

        with patch.object(self.ctrler, "chzdev") as m_chzdev:
            await self.ctrler.handle_zdevs()

        m_chzdev.assert_not_called()

    async def test_handle_zdevs(self):
        self.ctrler.load_autoinstall_data(
            [
                {"id": "0.0.1507", "enabled": True},
                {"id": "0.0.1508", "enabled": False},
            ]
        )

        with patch.object(self.ctrler, "chzdev") as m_chzdev:
            await self.ctrler.handle_zdevs()

        expected_calls = [
            unittest.mock.call("enable", self.ctrler.zdevinfos["0.0.1507"]),
            unittest.mock.call("disable", self.ctrler.zdevinfos["0.0.1508"]),
        ]

        self.assertEqual(expected_calls, m_chzdev.mock_calls)

    async def test_chzdev_wrong_action(self):
        self.ctrler.done_ai_actions = []
        with self.assertRaises(ValueError):
            await self.ctrler.chzdev("enAble", self.ctrler.zdevinfos["0.0.1507"])
        self.assertFalse(self.ctrler.done_ai_actions)

    @patch("asyncio.sleep", AsyncMock())
    async def test_chzdev_enable(self):
        self.ctrler.done_ai_actions = []

        self.ctrler.app.command_runner = Mock()
        with patch.object(self.ctrler.app.command_runner, "run", AsyncMock()) as m_run:
            await self.ctrler.chzdev("enable", self.ctrler.zdevinfos["0.0.1507"])

        m_run.assert_called_once_with(["chzdev", "--enable", "0.0.1507"])

        self.assertEqual(
            [ZdevAction(id="0.0.1507", enable=True)], self.ctrler.done_ai_actions
        )

    @patch("asyncio.sleep", AsyncMock())
    async def test_chzdev_disable(self):
        self.ctrler.done_ai_actions = []

        self.ctrler.app.command_runner = Mock()
        with patch.object(self.ctrler.app.command_runner, "run", AsyncMock()) as m_run:
            await self.ctrler.chzdev("disable", self.ctrler.zdevinfos["0.0.1507"])

        self.assertEqual(
            [ZdevAction(id="0.0.1507", enable=False)], self.ctrler.done_ai_actions
        )

        m_run.assert_called_once_with(["chzdev", "--disable", "0.0.1507"])

    @patch("asyncio.sleep", AsyncMock())
    async def test_chzdev_enable_disable_multiple(self):
        self.ctrler.done_ai_actions = []

        self.ctrler.app.command_runner = Mock()
        with patch.object(self.ctrler.app.command_runner, "run", AsyncMock()) as m_run:
            await self.ctrler.chzdev("enable", self.ctrler.zdevinfos["0.0.1507"])
            await self.ctrler.chzdev("enable", self.ctrler.zdevinfos["0.0.1507"])
            await self.ctrler.chzdev("disable", self.ctrler.zdevinfos["0.0.1508"])
            await self.ctrler.chzdev("enable", self.ctrler.zdevinfos["0.0.1508"])

        expected_calls = [
            unittest.mock.call(["chzdev", "--enable", "0.0.1507"]),
            unittest.mock.call(["chzdev", "--enable", "0.0.1507"]),
            unittest.mock.call(["chzdev", "--disable", "0.0.1508"]),
            unittest.mock.call(["chzdev", "--enable", "0.0.1508"]),
        ]
        self.assertEqual(expected_calls, m_run.mock_calls)

        self.assertEqual(
            [
                ZdevAction(id="0.0.1507", enable=True),
                ZdevAction(id="0.0.1507", enable=True),
                ZdevAction(id="0.0.1508", enable=False),
                ZdevAction(id="0.0.1508", enable=True),
            ],
            self.ctrler.done_ai_actions,
        )
