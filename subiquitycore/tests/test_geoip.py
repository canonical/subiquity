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

from subiquitycore.async_helpers import TaskFailure
from subiquitycore.geoip import GeoIP
from subiquitycore.tests import SubiTestCase
from subiquity.tests.mocks import make_app

xml = '''
<Response>
  <Ip>1.2.3.4</Ip>
  <Status>OK</Status>
  <CountryCode>US</CountryCode>
  <CountryCode3>USA</CountryCode3>
  <CountryName>United States</CountryName>
  <RegionCode>CA</RegionCode>
  <RegionName>California</RegionName>
  <City>Rio Vista</City>
  <ZipPostalCode>94571</ZipPostalCode>
  <Latitude>38.1637</Latitude>
  <Longitude>-121.7016</Longitude>
  <AreaCode>707</AreaCode>
  <TimeZone>America/Los_Angeles</TimeZone>
</Response>
'''
partial = '<Response>'
incomplete = '<Longitude>-121.7016</Longitude>'
long_cc = '<Response><CountryCode>USA</CountryCode></Response>'
empty_tz = '<Response><TimeZone></TimeZone></Response>'
empty_cc = '<Response><CountryCode></CountryCode></Response>'


class TestGeoIP(SubiTestCase):

    def setUp(self):
        self.geoip = GeoIP(make_app())
        self.geoip.response_text = xml
        self.geoip.load_element()

    def test_countrycode(self):
        self.assertEqual("us", self.geoip.countrycode)

    def test_timezone(self):
        self.assertEqual("America/Los_Angeles", self.geoip.timezone)


class TestGeoIPBadData(SubiTestCase):
    def setUp(self):
        self.geoip = GeoIP(make_app())

    def test_partial_reponse(self):
        self.geoip.response_text = partial
        with self.assertRaises(TaskFailure):
            self.geoip.load_element()

    def test_bad_ccs(self):
        for text in (incomplete, long_cc, empty_cc):
            self.geoip.response_text = text
            self.geoip.load_element()
            self.assertIsNone(self.geoip.countrycode)

    def test_bad_tzs(self):
        for text in (incomplete, empty_tz):
            self.geoip.response_text = text
            self.geoip.load_element()
            self.assertIsNone(self.geoip.timezone)
