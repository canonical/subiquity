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

import requests.exceptions
import requests_unixsocket

from subiquitycore.controller import BaseController
from subiquitycore import utils

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
        self.state = "loaded"

class SnapdSnapInfoLoader:

    def __init__(self, model, run_in_bg, sock):
        self.state = "not running"
        self.model = model
        self.run_in_bg = run_in_bg
        self.url_base = "http+unix://{}/v2/find?".format(quote_plus(sock))
        self.session = requests_unixsocket.Session()
        self.pending_info_snaps = []
        self.ongoing = {} # {snap:[callbacks]}

    def start(self):
        self.state = "loading list"
        log.debug("loading list of snaps")
        def cb():
            if self.state != "loading list":
                return
            self.state = "loading info"
            self.pending_info_snaps = self.model.get_snap_list()
            log.debug("fetched list of %s snaps", len(self.pending_info_snaps))
            self._fetch_next_info()
        self.ongoing[None] = [cb]
        self.run_in_bg(self._bg_fetch_list, self._fetched_list)

    def stop(self):
        self.state = "stopped"

    def _bg_fetch_list(self):
        return self.session.get(self.url_base + 'section=developers', timeout=60)

    def _fetched_list(self, fut):
        if self.state == "stopped":
            return
        try:
            response = fut.result()
            response.raise_for_status()
        except requests.exceptions.RequestException:
            log.exception("loading list of snaps failed")
            self.state = "failed"
        else:
            self.model.load_find_data(response.json())
        for cb in self.ongoing[None]:
            cb()
        del self.ongoing[None]

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
            self.state = "loaded"
            return
        snap = self.pending_info_snaps.pop(0)
        self._fetch_info_for_snap(snap, self._fetch_next_info)

    def _bg_fetch_next_info(self, snap):
        return self.session.get(self.url_base + 'name=' + snap.name, timeout=60)

    def _fetched_info(self, fut):
        if self.state == "stopped":
            return
        try:
            response = fut.result()
            response.raise_for_status()
        except requests.exceptions.RequestException:
            log.exception("loading list of snaps failed")
            self.state = "failed"
        else:
            data = response.json()
            snap = self.model.load_info_data(data)
            if snap is not None:
                log.debug("fetched info on %r", snap.name)
            else:
                log.debug("fetched info on mystery snap %s", data)
            for cb in self.ongoing.get(snap, []):
                cb()
            del self.ongoing[snap]


class SnapListController(BaseController):

    signals = [
        ('network-config-written', 'network_config_done'),
        ('network-proxy-set', 'proxy_config_done'),
    ]

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.snaplist
        self.loader = None
        self._maybe_start_new_loader()

    def _maybe_start_new_loader(self):
        if self.loader:
            if self.loader.state != "failed":
                return
            else:
                self.loader.stop()
        self.loader = SnapdSnapInfoLoader(self.model, self.run_in_bg, '/run/snapd.socket')
        self.loader.start()

    def network_config_done(self, netplan_path):
        self._maybe_start_new_loader()

    def proxy_config_done(self):
        log.debug("restarting snapd to pick up proxy config")
        if self.opts.dry_run:
            cmd = ['sleep', '0.5']
        else:
            cmd = ['systemctl', 'restart', 'snapd.service']
        self.run_in_bg(
            lambda: utils.run_command(cmd),
            lambda fut: self._maybe_start_new_loader())

    def default(self):
        if self.loader.state == "failed":
            # If loading snaps failed, skip the screen.
            self.done({})
            return
        self.ui.set_header(
            _("Featured Server Snaps"),
            )
        self.ui.set_body(SnapListView(self.model, self))

    def info_for_snap(self, snap, callback):
        self.loader.fetch_info_for_snap(snap, callback)

    def done(self, snaps_to_install):
        self.signal.emit_signal("next-screen")

    def cancel(self, sender=None):
        self.signal.emit_signal("prev-screen")
