# Copyright 2018 Canonical, Ltd.
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

import enum
import logging
import requests
from xml.etree import ElementTree

from subiquitycore.controller import BaseController

from subiquity.async_helpers import (
    run_in_thread,
    schedule_task,
    )
from subiquity.ui.views.mirror import MirrorView

log = logging.getLogger('subiquity.controllers.mirror')


class CheckState(enum.IntEnum):
    NOT_STARTED = enum.auto()
    CHECKING = enum.auto()
    FAILED = enum.auto()
    DONE = enum.auto()


class MirrorController(BaseController):

    signals = [
        ('snapd-network-change', 'snapd_network_changed'),
    ]

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model.mirror
        self.check_state = CheckState.NOT_STARTED
        if 'country-code' in self.answers:
            self.check_state = CheckState.DONE
            self.model.set_country(self.answers['country-code'])

    def snapd_network_changed(self):
        if self.check_state != CheckState.DONE:
            self.check_state = CheckState.CHECKING
            schedule_task(self.lookup())

    async def lookup(self):
        try:
            response = await run_in_thread(
                requests.get, "https://geoip.ubuntu.com/lookup")
            response.raise_for_status()
        except requests.exceptions.RequestException:
            log.exception("geoip lookup failed")
            self.check_state = CheckState.FAILED
            return
        try:
            e = ElementTree.fromstring(response.text)
        except ElementTree.ParseError:
            log.exception("parsing %r failed", response.text)
            self.check_state = CheckState.FAILED
            return
        cc = e.find("CountryCode")
        if cc is None:
            log.debug("no CountryCode found in %r", response.text)
            self.check_state = CheckState.FAILED
            return
        cc = cc.text.lower()
        if len(cc) != 2:
            log.debug("bogus CountryCode found in %r", response.text)
            self.check_state = CheckState.FAILED
            return
        self.check_state = CheckState.DONE
        self.model.set_country(cc)

    def start_ui(self):
        self.check_state = CheckState.DONE
        self.ui.set_body(MirrorView(self.model, self))
        if 'mirror' in self.answers:
            self.done(self.answers['mirror'])
        elif 'country-code' in self.answers \
             or 'accept-default' in self.answers:
            self.done(self.model.mirror)

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def serialize(self):
        return self.model.mirror

    def deserialize(self, data):
        self.model.mirror = data

    def done(self, mirror):
        log.debug("MirrorController.done next-screen mirror=%s", mirror)
        if mirror != self.model.mirror:
            self.model.mirror = mirror
        self.signal.emit_signal('next-screen')
