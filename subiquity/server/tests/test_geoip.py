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

from aioresponses import aioresponses

from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.util import run_coro
from subiquity.server.geoip import (
    GeoIP,
    HTTPGeoIPStrategy,
    )

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
        strategy = HTTPGeoIPStrategy()
        self.geoip = GeoIP(make_app(), strategy)

        async def fn():
            self.assertTrue(await self.geoip.lookup())

        with aioresponses() as mocked:
            mocked.get("https://geoip.ubuntu.com/lookup", body=xml)
            run_coro(fn())

    def test_countrycode(self):
        self.assertEqual("us", self.geoip.countrycode)

    def test_timezone(self):
        self.assertEqual("America/Los_Angeles", self.geoip.timezone)


class TestGeoIPBadData(SubiTestCase):
    def setUp(self):
        strategy = HTTPGeoIPStrategy()
        self.geoip = GeoIP(make_app(), strategy)

    def test_partial_reponse(self):
        async def fn():
            self.assertFalse(await self.geoip.lookup())
        with aioresponses() as mocked:
            mocked.get("https://geoip.ubuntu.com/lookup", body=partial)
            run_coro(fn())

    def test_incomplete(self):
        async def fn():
            self.assertFalse(await self.geoip.lookup())
        with aioresponses() as mocked:
            mocked.get("https://geoip.ubuntu.com/lookup", body=incomplete)
            run_coro(fn())
        self.assertIsNone(self.geoip.countrycode)
        self.assertIsNone(self.geoip.timezone)

    def test_long_cc(self):
        async def fn():
            self.assertFalse(await self.geoip.lookup())
        with aioresponses() as mocked:
            mocked.get("https://geoip.ubuntu.com/lookup", body=long_cc)
            run_coro(fn())
        self.assertIsNone(self.geoip.countrycode)

    def test_empty_cc(self):
        async def fn():
            self.assertFalse(await self.geoip.lookup())
        with aioresponses() as mocked:
            mocked.get("https://geoip.ubuntu.com/lookup", body=empty_cc)
            run_coro(fn())
        self.assertIsNone(self.geoip.countrycode)

    def test_empty_tz(self):
        async def fn():
            self.assertFalse(await self.geoip.lookup())
        with aioresponses() as mocked:
            mocked.get("https://geoip.ubuntu.com/lookup", body=empty_tz)
            run_coro(fn())
        self.assertIsNone(self.geoip.timezone)
