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

from subiquitycore.tests import SubiTestCase
from subiquity.common.geoip import GeoIP
from subiquity.tests.util import run_coro


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


class MockGeoIPResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self, *args, **kwargs):
        pass


def requests_get_factory(text):
    def requests_get(*args, **kwargs):
        return MockGeoIPResponse(text)
    return requests_get


class TestGeoIP(SubiTestCase):
    @mock.patch('requests.get', new=requests_get_factory(xml))
    def setUp(self):
        self.geoip = GeoIP()

        async def fn():
            self.assertTrue(await self.geoip.lookup())
        run_coro(fn())

    def test_countrycode(self):
        self.assertEqual("us", self.geoip.countrycode)

    def test_timezone(self):
        self.assertEqual("America/Los_Angeles", self.geoip.timezone)


class TestGeoIPBadData(SubiTestCase):
    def setUp(self):
        self.geoip = GeoIP()

    @mock.patch('requests.get', new=requests_get_factory(partial))
    def test_partial_reponse(self):
        async def fn():
            self.assertFalse(await self.geoip.lookup())
        run_coro(fn())

    @mock.patch('requests.get', new=requests_get_factory(incomplete))
    def test_incomplete(self):
        async def fn():
            self.assertTrue(await self.geoip.lookup())
        run_coro(fn())
        self.assertIsNone(self.geoip.countrycode)
        self.assertIsNone(self.geoip.timezone)

    @mock.patch('requests.get', new=requests_get_factory(long_cc))
    def test_long_cc(self):
        async def fn():
            self.assertTrue(await self.geoip.lookup())
        run_coro(fn())
        self.assertIsNone(self.geoip.countrycode)

    @mock.patch('requests.get', new=requests_get_factory(empty_cc))
    def test_empty_cc(self):
        async def fn():
            self.assertTrue(await self.geoip.lookup())
        run_coro(fn())
        self.assertIsNone(self.geoip.countrycode)

    @mock.patch('requests.get', new=requests_get_factory(empty_tz))
    def test_empty_tz(self):
        async def fn():
            self.assertTrue(await self.geoip.lookup())
        run_coro(fn())
        self.assertIsNone(self.geoip.timezone)
