# Copyright 2015 Canonical, Ltd.
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

import attr


log = logging.getLogger("subiquity.models.snaplist")


@attr.s(cmp=False)
class SnapInfo:
    name = attr.ib()
    summary = attr.ib()
    publisher = attr.ib()
    description = attr.ib()
    channels = attr.ib(default=attr.Factory(list))


@attr.s(cmp=False)
class ChannelSnapInfo:
    channel_name = attr.ib()
    revision = attr.ib()
    confinement = attr.ib()
    version = attr.ib()
    size = attr.ib()


class SnapListModel:
    """The overall model for subiquity."""

    def __init__(self, common):
        self._snap_info = []
        self._snaps_by_name = {}
        self._from_snapd()
        #self._from_sample_data()

    def _from_sample_data(self):
        opd = os.path.dirname
        opj = os.path.join
        snap_data_dir = opj(opd(opd(opd(__file__))), 'examples', 'snaps')
        snap_find_output = opj(snap_data_dir, 'find-output.json')
        with open(snap_find_output) as fp:
            self._load_find_data(json.load(fp))
        snap_info_glob = opj(snap_data_dir, 'info-*.json')
        for snap_info_file in glob.glob(snap_info_glob):
            with open(snap_info_file) as fp:
                self._load_info_data(json.load(fp))

    def _from_snapd(self):
        sock = "/run/snapd.socket"
        url = "http+unix://{}/v2/find?section=games".format(quote_plus(sock))
        import requests_unixsocket
        session = requests_unixsocket.Session()
        r = session.get(url)
        self._load_find_data(r.json())
        log.debug("%s", r.json())


    def _load_find_data(self, data):
        for s in data['result']:
            snap = SnapInfo(
                name=s['name'],
                summary=s['summary'],
                publisher=s['developer'],
                description=s['description'],
                )
            self._snap_info.append(snap)
            self._snaps_by_name[s['name']] = snap

    def _load_info_data(self, data):
        info = data['result'][0]
        snap = self._snaps_by_name.get(info['name'], None)
        if snap is None:
            return
        channel_map = info['channels']
        for track in info['tracks']:
            for risk in ["stable", "candidate", "beta", "edge"]:
                channel_name = '{}/{}'.format(track, risk)
                if channel_name in channel_map:
                    channel_data = channel_map[channel_name]
                    if track == "latest":
                        channel_name = risk
                    snap.channels.append(ChannelSnapInfo(
                        channel_name=channel_name,
                        revision=channel_data['revision'],
                        confinement=channel_data['confinement'],
                        version=channel_data['version'],
                        size=channel_data['size'],
                    ))

    def get_snap_list(self):
        return self._snap_info

    def set_installed_list(self, to_install):
        self.to_install = to_install
