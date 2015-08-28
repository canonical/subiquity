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
import json
import os
from probert.storage import (Storage,
                             StorageInfo)
from probert.network import (Network,
                             NetworkInfo)

log = logging.getLogger('subiquity.prober')

class Prober():
    def __init__(self, opts):
        self.opts = opts
        self.probe_data = {}

        if self.opts.machine_config:
            log.debug('User specified machine_config: {}'.format(
                        self.opts.machine_config))
            if os.path.exists(self.opts.machine_config):
                with open(self.opts.machine_config) as mc:
                    self.probe_data = json.load(mc)
        log.debug('Prober() init finished, data:{}'.format(self.probe_data))

    def get_network(self):
        if 'network' not in self.probe_data:
            log.debug('get_network: no network in probe_data, fetching')
            network = Network()
            results = network.probe()
            self.probe_data['network'] = results

        return self.probe_data['network']

    def get_network_info(self, device):
        ''' Load a NetworkInfo class for specified device '''
        return NetworkInfo({device: self.get_network().get(device)})

    def get_storage(self):
        ''' Load a StorageInfo class.  Probe if it's not present '''
        if 'storage' not in self.probe_data:
            log.debug('get_storage: no storage in probe_data, fetching')
            storage = Storage()
            results = storage.probe()
            self.probe_data['storage'] = results

        return self.probe_data['storage']

    def get_storage_info(self, device):
        ''' Load a StorageInfo class for specified device '''
        return StorageInfo({device: self.get_storage().get(device)})
