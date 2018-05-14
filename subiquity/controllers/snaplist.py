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

import glob
import json
import logging
import os
from urllib.parse import quote_plus

import requests_unixsocket

from subiquitycore.controller import BaseController

from subiquity.ui.views.snaplist import SnapListView

log = logging.getLogger('subiquity.controllers.snaplist')

class SnapInfoLoader:
    def __init__(self):
        pass

class SampleDataSnapInfoLoader:

    def __init__(self, model, snap_data_dir):
        self.model = model
        self.snap_data_dir = snap_data_dir

    def start(self):
        snap_find_output = os.path.join(self.snap_data_dir, 'find-output.json')
        with open(snap_find_output) as fp:
            self.model.load_find_data(json.load(fp))
        snap_info_glob = os.path.join(self.snap_data_dir, 'info-*.json')
        for snap_info_file in glob.glob(snap_info_glob):
            with open(snap_info_file) as fp:
                self.model.load_info_data(json.load(fp))

class SnapdSnapInfoLoader:

    def __init__(self, model, run_in_bg, sock):
        self.model = model
        self.run_in_bg = run_in_bg
        self.url_base = "http+unix://{}/v2/find?".format(quote_plus(sock))
        self.session = requests_unixsocket.Session()
        self.pending_info_snaps = []
        self.ongoing = {} # {snap:[callbacks]}

    def start(self):
        self.run_in_bg(self._bg_fetch_list, self._fetched_list)

    def _bg_fetch_list(self):
        return self.session.get(self.url_base + 'section=games')

    def _fetched_list(self, fut):
        self.model.load_find_data(fut.result().json())
        self.pending_info_snaps = self.model.get_snap_list()
        log.debug("fetched list of %s snaps", len(self.pending_info_snaps))
        self._fetch_next_info()

    def fetch_info_for_snap(self, snap, callback):
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
            self._fetched_info)

    def _fetch_next_info(self):
        if not self.pending_info_snaps:
            return
        snap = self.pending_info_snaps.pop(0)
        self._fetch_info_for_snap(snap, self._fetch_next_info)

    def _bg_fetch_next_info(self, snap):
        import time
        time.sleep(5)
        return self.session.get(self.url_base + 'name=' + snap.name)

    def _fetched_info(self, fut):
        data = fut.result().json()
        snap = self.model.load_info_data(data)
        if snap is not None:
            log.debug("fetched info on %r", snap.name)
        else:
            log.debug("fetched info on mystery snap %s", data)
        for f in self.ongoing[snap]:
            f()
        del self.ongoing[snap]


class SnapListController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.snaplist
        self.loader = SnapdSnapInfoLoader(self.model, self.run_in_bg, '/run/snapd.socket')
        self.loader.start()

    def default(self):
        self.ui.set_header(
            _("Featured Server Snaps"),
            )
        #if len(self.model.get_snap_list()) == 0:
        #    self.done({})
        #    return
        self.ui.set_body(SnapListView(self.model, self))

    def info_for_snap(self, snap, callback):
        self.loader.fetch_info_for_snap(snap, callback)

    def done(self, snaps_to_install):
        self.signal.emit_signal("next-screen")

    def cancel(self, sender=None):
        self.signal.emit_signal("prev-screen")
