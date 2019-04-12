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

import logging

import requests.exceptions

from subiquitycore.controller import BaseController
from subiquitycore.core import Skip

from subiquity.models.snaplist import SnapSelection
from subiquity.ui.views.snaplist import SnapListView

log = logging.getLogger('subiquity.controllers.snaplist')


class SnapdSnapInfoLoader:

    def __init__(self, model, run_in_bg, connection, store_section):
        self.model = model
        self.run_in_bg = run_in_bg
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

        def cb(snap_list):
            if not self._running:
                return
            self.snap_list_fetched = True
            self.pending_info_snaps = snap_list
            log.debug("fetched list of %s snaps", len(self.pending_info_snaps))
            self._fetch_next_info()
        self.ongoing[None] = [cb]
        self.run_in_bg(self._bg_fetch_list, self._fetched_list)

    def stop(self):
        self._running = False

    def _bg_fetch_list(self):
        return self.connection.get('v2/find', section=self.store_section)

    def _fetched_list(self, fut):
        if not self._running:
            return
        try:
            response = fut.result()
            response.raise_for_status()
        except requests.exceptions.RequestException:
            log.exception("loading list of snaps failed")
            self.failed = True
            self._running = False
        else:
            self.model.load_find_data(response.json())
        for cb in self.ongoing.pop(None):
            cb(self.model.get_snap_list())

    def get_snap_list(self, callback):
        if self.snap_list_fetched:
            callback(self.model.get_snap_list())
        elif None in self.ongoing:
            self.ongoing[None].append(callback)
        else:
            self.start()
            self.ongoing[None].append(callback)

    def get_snap_info(self, snap, callback):
        if len(snap.channels) > 0:
            callback()
            return
        if snap in self.ongoing:
            self.ongoing[snap].append(callback)
            return
        if snap in self.pending_info_snaps:
            self.pending_info_snaps.remove(snap)
        self._fetch_info_for_snap(snap, callback)

    def _fetch_info_for_snap(self, snap, callback):
        self.ongoing[snap] = [callback]
        log.debug('starting fetch for %s', snap.name)
        self.run_in_bg(
            lambda: self._bg_fetch_next_info(snap),
            lambda fut: self._fetched_info(snap, fut))

    def _fetch_next_info(self):
        if not self.pending_info_snaps:
            return
        snap = self.pending_info_snaps.pop(0)
        self._fetch_info_for_snap(snap, self._fetch_next_info)

    def _bg_fetch_next_info(self, snap):
        return self.connection.get('v2/find', name=snap.name)

    def _fetched_info(self, snap, fut):
        if not self._running:
            return
        try:
            response = fut.result()
            response.raise_for_status()
        except requests.exceptions.RequestException:
            log.exception("loading snap info failed")
            # XXX something better here?
        else:
            data = response.json()
            self.model.load_info_data(data)
        for cb in self.ongoing.pop(snap):
            cb()


class SnapListController(BaseController):

    signals = [
        ('snapd-network-change', 'snapd_network_changed'),
    ]

    def _make_loader(self):
        return SnapdSnapInfoLoader(
            self.model, self.run_in_bg, self.snapd_connection,
            self.opts.snap_section)

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.snaplist
        self.loader = self._make_loader()
        self.answers = self.all_answers.get('SnapList', {})

    def snapd_network_changed(self):
        # If the loader managed to load the list of snaps, the
        # network must basically be working.
        if self.loader.snap_list_fetched:
            return
        else:
            self.loader.stop()
        self.loader = self._make_loader()
        self.loader.start()

    def default(self):
        if self.loader.failed or not self.base_model.network.has_network:
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
        self.model.set_installed_list(snaps_to_install)
        self.signal.emit_signal("installprogress:snap-config-done")
        self.signal.emit_signal("next-screen")

    def cancel(self, sender=None):
        self.signal.emit_signal("prev-screen")
