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

import mock

from subiquity.common.types import TimeZoneInfo
from subiquity.models.timezone import TimeZoneModel
from subiquity.server.controllers.timezone import TimeZoneController
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.util import run_coro


class MockGeoIP:
    text = ''

    @property
    def timezone(self):
        return self.text


tz_denver = 'America/Denver'
tz_utc = 'Etc/UTC'


class TestTimeZoneController(SubiTestCase):
    def setUp(self):
        self.tzc_init()

    def tzc_init(self):
        self.tzc = TimeZoneController(make_app())
        self.tzc.model = TimeZoneModel()
        self.tzc.app.geoip = MockGeoIP()
        self.tzc.app.geoip.text = tz_denver

    @mock.patch('subiquity.server.controllers.timezone.timedatectl_settz')
    @mock.patch('subiquity.server.controllers.timezone.timedatectl_gettz')
    def test_good_tzs(self, tdc_gettz, tdc_settz):
        tdc_gettz.return_value = tz_utc
        goods = [
            # val - autoinstall value
            # |       settz - should system set timezone
            # |       |     geoip - did we get a value by geoip?
            # |       |     |     valid_lookup
            ('geoip', True, True, True),
            ('geoip', False, True, False),
            # empty val is valid and means to set no time zone
            ('', False, False, True),
            ('Pacific/Auckland', True, False, False),
            ('America/Denver', True, False, False),
        ]
        for val, settz, geoip, valid_lookup in goods:
            self.tzc_init()
            if not val or val == 'geoip':
                if valid_lookup:
                    tz = TimeZoneInfo(tz_denver, True)
                else:
                    tz = TimeZoneInfo(tz_utc, False)
                    self.tzc.app.geoip.text = ''
            else:
                tz = TimeZoneInfo(val, False)
            self.tzc.deserialize(val)
            self.assertEqual(val, self.tzc.serialize())
            self.assertEqual(settz, self.tzc.model.should_set_tz,
                             self.tzc.model)
            self.assertEqual(geoip, self.tzc.model.detect_with_geoip,
                             self.tzc.model)
            self.assertEqual(tz, run_coro(self.tzc.GET()), self.tzc.model)
            cloudconfig = {}
            if self.tzc.model.should_set_tz:
                cloudconfig = {'timezone': tz.timezone}
                tdc_settz.assert_called_with(tz.timezone)
            self.assertEqual(cloudconfig, self.tzc.model.make_cloudconfig(),
                             self.tzc.model)

    def test_bad_tzs(self):
        bads = [
            'dhcp',  # possible future value, not supported yet
            'notatimezone',
        ]
        for b in bads:
            with self.assertRaises(ValueError):
                self.tzc.deserialize(b)
