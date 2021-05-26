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

import asyncio
import logging
import requests
from xml.etree import ElementTree

from subiquitycore.async_helpers import (
    CheckedSingleInstanceTask,
    run_in_thread,
    TaskFailure,
)

log = logging.getLogger('subiquitycore.geoip')


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

    def __init__(self, app):
        self.app = app
        self.element = None
        self.response_text = ''
        self.valid = False
        self.lookup_task = task = CheckedSingleInstanceTask(self._lookup)
        self.app.hub.subscribe('network-up', task.start)
        self.app.hub.subscribe('network-proxy-set', task.start)

    async def lookup(self):
        await self.lookup_task.start()
        return self.valid

    async def _lookup(self):
        if self.valid:
            return
        await self.request_geoip_data()
        self.load_element()
        self.valid = True
        self.app.hub.broadcast('geoip-data-ready')

    async def request_geoip_data(self):
        try:
            response = await run_in_thread(
                requests.get, "https://geoip.ubuntu.com/lookup")
            response.raise_for_status()
            self.response_text = response.text
        except requests.exceptions.RequestException as re:
            raise TaskFailure(f'geoip lookup failed: {re}') from re

    async def wait_for(self, timeout, context):
        if not self.lookup_task.has_started():
            return
        try:
            with context.child('waiting'):
                await asyncio.wait_for(self.lookup_task.wait(), timeout)
        except asyncio.TimeoutError:
            pass

    def load_element(self):
        try:
            self.element = ElementTree.fromstring(self.response_text)
        except ElementTree.ParseError as pe:
            raise TaskFailure(f"parsing {self.response_text} failed") from pe
        return self.element is not None

    @property
    def timezone(self):
        if not self.element:
            return None
        tz = self.element.find("TimeZone")
        if tz is None or not tz.text:
            log.debug(f"no TimeZone found in {self.response_text}")
            return None
        return tz.text

    @property
    def countrycode(self):
        cc = self.element.find("CountryCode")
        if cc is None or cc.text is None:
            log.debug(f"no CountryCode found in {self.response_text}")
            return None
        cc = cc.text.lower()
        if len(cc) != 2:
            log.debug(f"bogus CountryCode found in {self.response_text}")
            return None
        return cc
