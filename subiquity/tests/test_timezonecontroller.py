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

from subiquity.models.timezone import TimeZoneModel
from subiquity.server.controllers.timezone import TimeZoneController
from subiquity.tests.mocks import make_app
from subiquitycore.tests import SubiTestCase


class TestTimeZoneController(SubiTestCase):

    def setUp(self):
        self.tzc = TimeZoneController(make_app())
        self.tzc.model = TimeZoneModel()

    def test_good_tzs(self):
        goods = [
            # val     settz  geoip
            ('geoip', False, True),
            ('Pacific/Auckland', True, False),
            ('America/Denver', True, False),
            ('', False, False),  # empty is valid and means to set no time zone
        ]
        for val, settz, geoip in goods:
            self.tzc.deserialize(val)
            self.assertEqual(val, self.tzc.serialize())
            self.assertEqual(settz, self.tzc.model.should_set_tz,
                             self.tzc.model)
            self.assertEqual(geoip, self.tzc.model.detect_with_geoip,
                             self.tzc.model)

    def test_bad_tzs(self):
        bads = [
            'dhcp',  # possible future value, not supported yet
            'notatimezone',
        ]
        for b in bads:
            with self.assertRaises(ValueError):
                self.tzc.deserialize(b)
