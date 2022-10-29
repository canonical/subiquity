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

from parameterized import parameterized

from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app

from subiquity.server.controllers.shutdown import ShutdownController
from subiquity.common.types import ShutdownMode


class TestSubiquityModel(SubiTestCase):
    def setUp(self):
        self.app = make_app()
        self.controller = ShutdownController(self.app)

    @parameterized.expand([
        [{'shutdown': 'reboot'}],
        [{'shutdown': 'poweroff'}],
        [{'shutdown': 'wait'}],
    ])
    async def test_load_ai(self, ai_data):
        expected = ai_data.get('shutdown')
        self.controller.load_autoinstall_data(expected)
        self.assertEqual(self.controller.mode.value, expected)
        self.assertEqual(self.controller.mode, ShutdownMode(expected))

    async def test_supported_values(self):
        actual = ShutdownController.autoinstall_schema['enum']
        expected = ['reboot', 'poweroff', 'wait']
        self.assertEqual(expected, actual)
