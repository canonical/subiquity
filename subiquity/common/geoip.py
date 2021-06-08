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

log = logging.getLogger('subiquity.common.geoip')


class GeoIP:
    def __init__(self):
        self.element = None

    async def lookup(self):
        try:
            response = await run_in_thread(
                requests.get, "https://geoip.ubuntu.com/lookup")
            response.raise_for_status()
        except requests.exceptions.RequestException:
            log.exception("geoip lookup failed")
            return False
        self.response_text = response.text
        try:
            self.element = ElementTree.fromstring(self.response_text)
        except ElementTree.ParseError:
            log.exception("parsing %r failed", self.response_text)
            return False
        return True

    @property
    def countrycode(self):
        if not self.element:
            return None
        cc = self.element.find("CountryCode")
        if cc is None or cc.text is None:
            log.debug("no CountryCode found in %r", self.response_text)
            return None
        cc = cc.text.lower()
        if len(cc) != 2:
            log.debug("bogus CountryCode found in %r", self.response_text)
            return None
        return cc

    @property
    def timezone(self):
        if not self.element:
            return None
        tz = self.element.find("TimeZone")
        if tz is None or not tz.text:
            log.debug("no TimeZone found in %r", self.response_text)
            return None
        return tz.text
