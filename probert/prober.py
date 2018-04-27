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

from probert.storage import Storage
from probert.network import NetworkProber


class Prober():
    def __init__(self):
        self._results = {}

    def probe_all(self):
        self.probe_storage()
        self.probe_network()

    def probe_storage(self):
        self._results['storage'] = Storage().probe()

    def probe_network(self):
        self._results['network'] = NetworkProber().probe()

    def get_results(self):
        return self._results
