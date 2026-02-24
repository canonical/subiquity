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

from unittest import mock

import jsonschema
from jsonschema.validators import validator_for

from subiquity.models.timezone import TimeZoneModel
from subiquity.server.autoinstall import AutoinstallError
from subiquity.server.controllers.timezone import TimeZoneController
from subiquity.tests.test_timezonecontroller import MockGeoIP, tz_denver
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app


class TestTimeZoneController(SubiTestCase):
    def setUp(self):
        self.tzc_init()

    def tzc_init(self):
        self.tzc = TimeZoneController(make_app())
        self.tzc.model = TimeZoneModel()
        self.tzc.app.geoip = MockGeoIP()
        self.tzc.app.geoip.text = tz_denver

    def test_load_autoinstall_data(self):
        data = "Europe/Kyiv"
        with mock.patch.object(self.tzc, "deserialize"):
            self.tzc.load_autoinstall_data(data)

    def test_load_autoinstall_data__invalid_timezone(self):
        data = "Europe/Kiev"
        with mock.patch.object(
            self.tzc,
            "deserialize",
            side_effect=ValueError('Unrecognized time zone request "Europe/Kiev"'),
        ):
            with self.assertRaises(AutoinstallError):
                self.tzc.load_autoinstall_data(data)

    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            TimeZoneController.autoinstall_schema
        )

        JsonValidator.check_schema(TimeZoneController.autoinstall_schema)
