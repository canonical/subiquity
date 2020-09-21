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

import datetime
import logging

from subiquity.common.types import (
    ChannelSnapInfo,
    SnapInfo,
    )


log = logging.getLogger("subiquity.models.snaplist")

risks = ["stable", "candidate", "beta", "edge"]


class SnapListModel:
    """The overall model for subiquity."""

    def __init__(self):
        self._snap_info = []
        self._snaps_by_name = {}
        self.selections = []  # [SnapSelection]
        self.complete_snaps = set()

    def _snap_for_name(self, name):
        s = self._snaps_by_name.get(name)
        if s is None:
            s = self._snaps_by_name[name] = SnapInfo(name=name)
            self._snap_info.append(s)
        return s

    def load_find_data(self, data):
        for info in data['result']:
            self.update(self._snap_for_name(info['name']), info)

    def add_partial_snap(self, name):
        self._snaps_for_name(name)

    def update(self, snap, data):
        snap.summary = data['summary']
        snap.publisher = data['developer']
        snap.verified = data['publisher']['validation'] == "verified"
        snap.description = data['description']
        snap.confinement = data['confinement']
        snap.license = data['license']
        self.complete_snaps.add(snap)

    def load_info_data(self, data):
        info = data['result'][0]
        snap = self._snaps_by_name.get(info['name'])
        if snap is None:
            return
        if snap not in self.complete_snaps:
            self.update_snap(snap, info)
        channel_map = info['channels']
        for track in info['tracks']:
            for risk in risks:
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
                        released_at=datetime.datetime.strptime(
                            channel_data['released-at'],
                            '%Y-%m-%dT%H:%M:%S.%fZ'),
                    ))
        return snap

    def get_snap_list(self):
        return self._snap_info[:]

    def set_installed_list(self, selections):
        for selection in selections:
            self._snap_for_name(selection.name)
        self.selections = selections
