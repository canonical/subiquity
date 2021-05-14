# Copyright 2018-2021 Canonical, Ltd.
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

import logging
import requests
from xml.etree import ElementTree

from subiquitycore.async_helpers import run_in_thread

log = logging.getLogger('subiquitycore.geoip')

# FIXME Q for mwhudson: Is this something we should worry about?
# https://docs.python.org/3/library/xml.html#xml-vulnerabilities


class GeoIP:
    """query geoip for CountryCode, TimeZone, other useful things"""

    # sample:
    #   <Response>
    #     <Ip>1.2.3.4</Ip>
    #     <Status>OK</Status>
    #     <CountryCode>US</CountryCode>
    #     <CountryCode3>USA</CountryCode3>
    #     <CountryName>United States</CountryName>
    #     <RegionCode>CA</RegionCode>
    #     <RegionName>California</RegionName>
    #     <City>Rio Vista</City>
    #     <ZipPostalCode>94571</ZipPostalCode>
    #     <Latitude>38.1637</Latitude>
    #     <Longitude>-121.7016</Longitude>
    #     <AreaCode>707</AreaCode>
    #     <TimeZone>America/Los_Angeles</TimeZone>
    #   </Response>

    def __init__(self):
        self.element = None
        self.response_text = ''

    async def lookup(self):
        await self.request_geoip_data()
        self._load_element()

    async def request_geoip_data(self):
        try:
            response = await run_in_thread(
                requests.get, "https://geoip.ubuntu.com/lookup")
            response.raise_for_status()
            self.response_text = response.text
        except requests.exceptions.RequestException as re:
            raise RuntimeError("geoip lookup failed") from re

    def _load_element(self):
        try:
            self.element = ElementTree.fromstring(self.response_text)
        except ElementTree.ParseError as pe:
            raise RuntimeError(f"parsing {self.response_text} failed") from pe

    def get_time_zone(self):
        tz = self.element.find("TimeZone")
        if tz is None or not tz.text:
            raise RuntimeError(f"no TimeZone found in {self.response_text}")
        return tz.text

    def get_country_code(self):
        cc = self.element.find("CountryCode")
        if cc is None or cc.text is None:
            raise RuntimeError(f"no CountryCode found in {self.response_text}")
        cc = cc.text.lower()
        if len(cc) != 2:
            raise RuntimeError(
                f"bogus CountryCode found in {self.response_text}")
        return cc
