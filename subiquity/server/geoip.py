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
import enum
import requests
from xml.etree import ElementTree

from subiquitycore.async_helpers import (
    run_in_thread,
    SingleInstanceTask,
)

from subiquity.server.types import InstallerChannels

log = logging.getLogger('subiquity.common.geoip')


class CheckState(enum.IntEnum):
    NOT_STARTED = enum.auto()
    CHECKING = enum.auto()
    FAILED = enum.auto()
    DONE = enum.auto()


class GeoIP:
    def __init__(self, app):
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
