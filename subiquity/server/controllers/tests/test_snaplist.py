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

import unittest
from unittest.mock import AsyncMock, Mock

import requests

from subiquity.models.snaplist import SnapListModel
from subiquity.server.controllers.snaplist import (
    SnapdSnapInfoLoader,
    SnapListFetchError,
)
from subiquitycore.tests.mocks import make_app


class TestSnapdSnapInfoLoader(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.model = SnapListModel()
        self.app = make_app()
        self.app.snapd = AsyncMock()
        self.app.report_start_event = Mock()
        self.app.report_finish_event = Mock()

        self.loader = SnapdSnapInfoLoader(
            self.model, self.app.snapd, "server", self.app.context
        )

    async def test_list_task_not_started(self):
        self.assertFalse(self.loader.fetch_list_completed())
        self.assertFalse(self.loader.fetch_list_failed())

    async def test_list_task_failed(self):
        self.app.snapd.get.side_effect = requests.exceptions.RequestException
        self.loader.start()
        await self.loader.load_list_task_created.wait()
        with self.assertRaises(SnapListFetchError):
            await self.loader.get_snap_list_task()
        self.assertFalse(self.loader.fetch_list_completed())
        self.assertTrue(self.loader.fetch_list_failed())

    async def test_list_task_completed(self):
        self.app.snapd.get.return_value = {"result": []}
        self.loader.start()
        await self.loader.load_list_task_created.wait()
        await self.loader.get_snap_list_task()
        self.assertTrue(self.loader.fetch_list_completed())
        self.assertFalse(self.loader.fetch_list_failed())
