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

from abc import ABC, abstractmethod
import aiohttp
import logging
import enum
from xml.etree import ElementTree

from subiquitycore.async_helpers import (
    SingleInstanceTask,
)

from subiquity.server.types import InstallerChannels

log = logging.getLogger('subiquity.server.geoip')


class CheckState(enum.IntEnum):
    NOT_STARTED = enum.auto()
    CHECKING = enum.auto()
    FAILED = enum.auto()
    DONE = enum.auto()


class LookupError(Exception):
    """ Error to raise when retrieving the GeoIP information. """


class GeoIPStrategy(ABC):
    """ Base class for strategies (e.g. HTTP or dry-run) to retrieve the GeoIP
    information. """
    @abstractmethod
    async def get_response(self) -> str:
        """ Return the GeoIP information as an XML document. """


class DryRunGeoIPStrategy(GeoIPStrategy):
    """ Dry-run implementation to retrieve GeoIP information. """
    async def get_response(self) -> str:
        """ Return the GeoIP information as an XML document. """
        return """\
<?xml version="1.0" encoding="UTF-8"?>
  <Response>
    <Ip>255.255.255.255</Ip>
    <Status>OK</Status>
    <CountryCode>FR</CountryCode>
    <CountryCode3>FRA</CountryCode3>
    <CountryName>France</CountryName>
    <RegionCode>A8</RegionCode>
    <RegionName>Ile-de-France</RegionName>
    <City>Paris</City>
    <ZipPostalCode>75013</ZipPostalCode>
    <Latitude>48.8151</Latitude>
    <Longitude>2.2182</Longitude>
    <AreaCode>0</AreaCode>
    <TimeZone>Europe/Paris</TimeZone>
  </Response>
"""


class HTTPGeoIPStrategy(GeoIPStrategy):
    """ HTTP implementation to retrieve GeoIP information. We use the
    geoip.ubuntu.com service. """
    async def get_response(self) -> str:
        url = "https://geoip.ubuntu.com/lookup"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    return await response.text()
        except aiohttp.ClientError as e:
            raise LookupError from e


class GeoIP:
    def __init__(self, app, strategy: GeoIPStrategy):
        self.app = app
        self.element = None
        self.cc = None
        self.tz = None
        self.check_state = CheckState.NOT_STARTED
        self.lookup_task = SingleInstanceTask(self.lookup)
        self.app.hub.subscribe(InstallerChannels.NETWORK_UP,
                               self.maybe_start_check)
        self.app.hub.subscribe(InstallerChannels.NETWORK_PROXY_SET,
                               self.maybe_start_check)
        self.strategy = strategy

    def maybe_start_check(self):
        if self.check_state != CheckState.DONE:
            self.check_state = CheckState.CHECKING
            self.lookup_task.start_sync()

    async def lookup(self):
        rv = await self._lookup()
        if rv:
            self.check_state = CheckState.DONE
        else:
            self.check_state = CheckState.FAILED
        return rv

    async def _lookup(self):
        try:
            self.response_text = await self.strategy.get_response()
        except LookupError:
            log.exception("geoip lookup failed")
            return False
        try:
            self.element = ElementTree.fromstring(self.response_text)
        except ElementTree.ParseError:
            log.exception("parsing %r failed", self.response_text)
            return False

        changed = False
        cc = self.element.find("CountryCode")
        if cc is None or cc.text is None:
            log.debug("no CountryCode found in %r", self.response_text)
            return False
        cc = cc.text.lower()
        if len(cc) != 2:
            log.debug("bogus CountryCode found in %r", self.response_text)
            return False
        if cc != self.cc:
            changed = True
            self.cc = cc

        tz = self.element.find("TimeZone")
        if tz is None or not tz.text:
            log.debug("no TimeZone found in %r", self.response_text)
            return False
        if tz != self.tz:
            changed = True
            self.tz = tz.text

        if changed:
            self.app.hub.broadcast(InstallerChannels.GEOIP)

        return True

    @property
    def countrycode(self):
        return self.cc

    @property
    def timezone(self):
        return self.tz
