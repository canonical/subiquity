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

import attr

@attr.s(cmp=False)
class SnapInfo:
    name = attr.ib()
    summary = attr.ib()
    publisher = attr.ib()
    description = attr.ib()
    channels = attr.ib(default=attr.Factory(list))


@attr.s(cmp=False)
class ChannelSnapInfo:
    revision = attr.ib()
    confinement = attr.ib()
    version = attr.ib()
    channel = attr.ib()
    epoch = attr.ib()
    size = attr.ib()

class SnapListModel:
    """The overall model for subiquity."""

    def __init__(self, common):
        pass

    def get_snap_list(self):
        return [
            Snap("etcd", "Resilient key-value store by CoreOS", "tvansteenburgh", "Etcd is a high availability key-value store, implementing the RAFT algorithm to deal with failover within the etcd cluster.  Popular in the Docker community as a shared store of small but important data in a distributed application."),
            ]


    def set_installed_list(self, to_install):
        self.to_install = to_install
