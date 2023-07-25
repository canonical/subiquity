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

import subprocess
import unittest
from unittest import mock

from subiquity.models.network import NetworkModel


class TestNetworkModel(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.model = NetworkModel()

    async def test_is_nm_enabled(self):
        with mock.patch("subiquity.models.network.arun_command") as arun:
            arun.return_value = subprocess.CompletedProcess([], 0)
            arun.return_value.stdout = "enabled\n"
            self.assertTrue(await self.model.is_nm_enabled())

        with mock.patch("subiquity.models.network.arun_command") as arun:
            arun.return_value = subprocess.CompletedProcess([], 0)
            arun.return_value.stdout = "disabled\n"
            self.assertFalse(await self.model.is_nm_enabled())

        with mock.patch("subiquity.models.network.arun_command") as arun:
            arun.side_effect = FileNotFoundError
            self.assertFalse(await self.model.is_nm_enabled())

        with mock.patch("subiquity.models.network.arun_command") as arun:
            arun.side_effect = subprocess.CalledProcessError(1, [], None, "error")
            self.assertFalse(await self.model.is_nm_enabled())
