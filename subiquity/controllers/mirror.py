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

import asyncio
import enum
import logging
import requests
from xml.etree import ElementTree

from curtin.config import merge_config

from subiquitycore.async_helpers import (
    run_in_thread,
    SingleInstanceTask,
    )

from subiquity.controller import SubiquityController
from subiquity.ui.views.mirror import MirrorView

log = logging.getLogger('subiquity.controllers.mirror')


class CheckState(enum.IntEnum):
    NOT_STARTED = enum.auto()
    CHECKING = enum.auto()
    FAILED = enum.auto()
    DONE = enum.auto()


class MirrorController(SubiquityController):

    autoinstall_key = "apt"
    model_name = "mirror"
    signals = [
        ('snapd-network-change', 'snapd_network_changed'),
    ]

    def __init__(self, app):
        self.ai_data = {}
        super().__init__(app)
        self.check_state = CheckState.NOT_STARTED
        if 'country-code' in self.answers:
            self.check_state = CheckState.DONE
            self.model.set_country(self.answers['country-code'])
        self.lookup_task = SingleInstanceTask(self.lookup)
        self.geoip_enabled = True

    def load_autoinstall_data(self, data):
        if data is None:
            return
        geoip = data.pop('geoip', True)
        merge_config(self.model.config, data)
        self.geoip_enabled = geoip and self.model.is_default()

    async def apply_autoinstall_config(self):
        if not self.geoip_enabled:
            return
        try:
            await asyncio.wait_for(self.lookup_task.wait(), 10)
        except asyncio.TimeoutError:
            pass

    def snapd_network_changed(self):
        if not self.geoip_enabled:
            return
        if self.check_state != CheckState.DONE:
            self.check_state = CheckState.CHECKING
            self.lookup_task.start_sync()

    async def lookup(self):
        with self.context.child("lookup"):
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
            self.done(self.model.get_mirror())

    def cancel(self):
        self.app.prev_screen()

    def serialize(self):
        return self.model.get_mirror()

    def deserialize(self, data):
        super().deserialize(data)
        self.model.set_mirror(data)

    def done(self, mirror):
        log.debug("MirrorController.done next_screen mirror=%s", mirror)
        if mirror != self.model.get_mirror():
            self.model.set_mirror(mirror)
        self.configured()
        self.app.next_screen()
