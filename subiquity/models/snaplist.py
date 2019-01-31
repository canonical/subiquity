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

import logging

import attr


log = logging.getLogger("subiquity.models.snaplist")


@attr.s(cmp=False)
class SnapInfo:
    name = attr.ib()
    summary = attr.ib()
    publisher = attr.ib()
    verified = attr.ib()
    description = attr.ib()
    confinement = attr.ib()
    license = attr.ib()
    channels = attr.ib(default=attr.Factory(list))


@attr.s(cmp=False)
class ChannelSnapInfo:
    channel_name = attr.ib()
    revision = attr.ib()
    confinement = attr.ib()
    version = attr.ib()
    size = attr.ib()


@attr.s(cmp=False)
class SnapSelection:
    channel = attr.ib()
    is_classic = attr.ib()


risks = ["stable", "candidate", "beta", "edge"]


class SnapListModel:
    """The overall model for subiquity."""

    def __init__(self):
        self._snap_info = []
        self._snaps_by_name = {}
        self.to_install = {}  # snap_name -> SnapSelection

    def load_find_data(self, data):
        for s in data['result']:
            snap = SnapInfo(
                name=s['name'],
                summary=s['summary'],
                publisher=s['developer'],
                verified=s['publisher']['validation'] == "verified",
                description=s['description'],
                confinement=s['confinement'],
                license=s['license'],
                )
            self._snap_info.append(snap)
            self._snaps_by_name[s['name']] = snap

    def load_info_data(self, data):
        info = data['result'][0]
        snap = self._snaps_by_name.get(info['name'])
        if snap is None:
            return
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
                    ))
        return snap

    def get_snap_list(self):
        return self._snap_info[:]

    def set_installed_list(self, to_install):
        self.to_install = to_install
