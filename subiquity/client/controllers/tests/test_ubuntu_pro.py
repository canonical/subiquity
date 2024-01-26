# Copyright 2024 Canonical, Ltd.
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
from unittest.mock import AsyncMock, patch

from subiquity.client.controllers.ubuntu_pro import UbuntuProController
from subiquity.common.types import UbuntuProResponse
from subiquitycore.tests.mocks import make_app
from subiquitycore.tuicontroller import Skip


class TestUbuntuProController(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        app = make_app()
        app.client = AsyncMock()

        self.ctrler = UbuntuProController(app)

    @patch("subiquity.client.controllers.ubuntu_pro.UbuntuProView")
    @patch(
        "subiquity.client.controllers.ubuntu_pro.lsb_release",
        return_value={"description": "Ubuntu 22.04 LTS", "release": "22.04"},
    )
    async def test_make_ui__lts(self, release, view):
        ctrler = self.ctrler

        rv = UbuntuProResponse(token="", has_network=False)

        with patch.object(ctrler.endpoint, "GET", return_value=rv):
            await ctrler.make_ui()

        view.assert_called_once_with(
            ctrler, token="", has_network=False, pre_release=False
        )

    @patch("subiquity.client.controllers.ubuntu_pro.UbuntuProView")
    @patch(
        "subiquity.client.controllers.ubuntu_pro.lsb_release",
        return_value={"description": "Ubuntu 23.10", "release": "23.10"},
    )
    async def test_make_ui__not_lts(self, release, view):
        with self.assertRaises(Skip):
            await self.ctrler.make_ui()

        view.assert_not_called()

    @patch("subiquity.client.controllers.ubuntu_pro.UbuntuProView")
    @patch(
        "subiquity.client.controllers.ubuntu_pro.lsb_release",
        return_value={
            "description": "Ubuntu Noble Numbat (development branch)",
            "release": "24.04",
        },
    )
    async def test_make_ui__noble_devel(self, release, view):
        ctrler = self.ctrler

        rv = UbuntuProResponse(token="", has_network=False)

        with patch.object(ctrler.endpoint, "GET", return_value=rv):
            await ctrler.make_ui()

        view.assert_called_once()

        view.assert_called_once_with(
            ctrler, token="", has_network=False, pre_release=True
        )
