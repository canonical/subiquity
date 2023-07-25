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

import aiohttp
from aioresponses import aioresponses

from subiquity.server.geoip import GeoIP, HTTPGeoIPStrategy
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app

xml = """
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
"""
partial = "<Response>"
incomplete = "<Longitude>-121.7016</Longitude>"
long_cc = "<Response><CountryCode>USA</CountryCode></Response>"
empty_tz = "<Response><TimeZone></TimeZone></Response>"
empty_cc = "<Response><CountryCode></CountryCode></Response>"


class TestGeoIP(SubiTestCase):
    async def asyncSetUp(self):
        strategy = HTTPGeoIPStrategy()
        self.geoip = GeoIP(make_app(), strategy)

        with aioresponses() as mocked:
            mocked.get("https://geoip.ubuntu.com/lookup", body=xml)
            self.assertTrue(await self.geoip.lookup())

    def test_countrycode(self):
        self.assertEqual("us", self.geoip.countrycode)

    def test_timezone(self):
        self.assertEqual("America/Los_Angeles", self.geoip.timezone)


class TestGeoIPBadData(SubiTestCase):
    def setUp(self):
        strategy = HTTPGeoIPStrategy()
        self.geoip = GeoIP(make_app(), strategy)

    async def test_partial_reponse(self):
        with aioresponses() as mocked:
            mocked.get("https://geoip.ubuntu.com/lookup", body=partial)
            self.assertFalse(await self.geoip.lookup())

    async def test_incomplete(self):
        with aioresponses() as mocked:
            mocked.get("https://geoip.ubuntu.com/lookup", body=incomplete)
            self.assertFalse(await self.geoip.lookup())
        self.assertIsNone(self.geoip.countrycode)
        self.assertIsNone(self.geoip.timezone)

    async def test_long_cc(self):
        with aioresponses() as mocked:
            mocked.get("https://geoip.ubuntu.com/lookup", body=long_cc)
            self.assertFalse(await self.geoip.lookup())
        self.assertIsNone(self.geoip.countrycode)

    async def test_empty_cc(self):
        with aioresponses() as mocked:
            mocked.get("https://geoip.ubuntu.com/lookup", body=empty_cc)
            self.assertFalse(await self.geoip.lookup())
        self.assertIsNone(self.geoip.countrycode)

    async def test_empty_tz(self):
        with aioresponses() as mocked:
            mocked.get("https://geoip.ubuntu.com/lookup", body=empty_tz)
            self.assertFalse(await self.geoip.lookup())
        self.assertIsNone(self.geoip.timezone)

    async def test_lookup_error(self):
        with aioresponses() as mocked:
            mocked.get(
                "https://geoip.ubuntu.com/lookup",
                exception=aiohttp.ClientError("lookup failure"),
            )
            self.assertFalse(await self.geoip.lookup())
        self.assertIsNone(self.geoip.timezone)
