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

from functools import partial
import logging

import requests.exceptions

from subiquitycore.controller import BaseController
from subiquitycore.core import Skip

from subiquity.models.snaplist import SnapSelection
from subiquity.ui.views.snaplist import SnapListView

log = logging.getLogger('subiquity.controllers.snaplist')


class SnapdSnapInfoLoader:

    def __init__(self, model, app, connection, store_section):
        self.model = model
        self.app = app
        self.store_section = store_section

        self._running = False
        self.snap_list_fetched = False
        self.failed = False

        self.connection = connection
        self.pending_info_snaps = []
        self.ongoing = {}  # {snap:[callbacks]}

    def start(self):
        self._running = True
        log.debug("loading list of snaps")
        self.app.schedule_task(self._start())

    async def _start(self):
        self.ongoing[None] = []
        try:
            response = await self.app.run_in_thread(
                partial(
                    self.connection.get,
                    'v2/find',
                    section=self.store_section))
            response.raise_for_status()
        except requests.exceptions.RequestException:
            log.exception("loading list of snaps failed")
            self.failed = True
            self._running = False
            return
        if not self._running:
            return
        self.model.load_find_data(response.json())
        self.snap_list_fetched = True
        self.pending_snaps = self.model.get_snap_list()
        log.debug("fetched list of %s snaps", len(self.model.get_snap_list()))
        for cb in self.ongoing.pop(None):
            cb()
        while self.pending_snaps and self._running:
            snap = self.pending_snaps.pop(0)
            self.ongoing[snap] = []
            await self._fetch_info_for_snap(snap)

    def stop(self):
        self._running = False

    async def _fetch_info_for_snap(self, snap):
        log.debug('starting fetch for %s', snap.name)
        try:
            response = await self.app.run_in_thread(
                partial(
                    self.connection.get,
                    'v2/find',
                    name=snap.name))
            response.raise_for_status()
        except requests.exceptions.RequestException:
            log.exception("loading snap info failed")
            # XXX something better here?
            return
        if not self._running:
            return
        data = response.json()
        log.debug('got data for %s', snap.name)
        self.model.load_info_data(data)
        for cb in self.ongoing.pop(snap):
            cb()

    def get_snap_list(self, callback):
        if self.snap_list_fetched:
            callback()
        elif None in self.ongoing:
            self.ongoing[None].append(callback)
        else:
            self.start()
            self.ongoing[None].append(callback)

    def get_snap_info(self, snap, callback):
        if len(snap.channels) > 0:
            callback()
            return
        if snap not in self.ongoing:
            if snap in self.pending_snaps:
                self.pending_snaps.remove(snap)
            self.ongoing[snap] = []
            self.app.schedule_task(
                self._fetch_info_for_snap(snap))
        self.ongoing[snap].append(callback)


class SnapListController(BaseController):

    signals = [
        ('snapd-network-change', 'snapd_network_changed'),
    ]

    def _make_loader(self):
        return SnapdSnapInfoLoader(
            self.model, self.app, self.app.snapd_connection,
            self.opts.snap_section)

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model.snaplist
        self.loader = self._make_loader()

    def snapd_network_changed(self):
        # If the loader managed to load the list of snaps, the
        # network must basically be working.
        if self.loader.snap_list_fetched:
            return
        else:
            self.loader.stop()
        self.loader = self._make_loader()
        self.loader.start()

    def start_ui(self):
        if self.loader.failed or not self.app.base_model.network.has_network:
            # If loading snaps failed or the network is disabled, skip the
            # screen.
            self.signal.emit_signal("installprogress:snap-config-done")
            raise Skip()
        if 'snaps' in self.answers:
            to_install = {}
            for snap_name, selection in self.answers['snaps'].items():
                to_install[snap_name] = SnapSelection(**selection)
            self.done(to_install)
            return
        self.ui.set_body(SnapListView(self.model, self))

    def get_snap_list(self, callback):
        self.loader.get_snap_list(callback)

    def get_snap_info(self, snap, callback):
        self.loader.get_snap_info(snap, callback)

    def done(self, snaps_to_install):
        log.debug(
            "SnapListController.done next-screen snaps_to_install=%s",
            snaps_to_install)
        self.model.set_installed_list(snaps_to_install)
        self.signal.emit_signal("installprogress:snap-config-done")
        self.signal.emit_signal("next-screen")

    def cancel(self, sender=None):
        self.signal.emit_signal("prev-screen")
