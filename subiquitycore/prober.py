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
import yaml
from probert.network import (StoredDataObserver,
                             UdevObserver)
from probert.storage import Storage

log = logging.getLogger('subiquitycore.prober')


class Prober():
    def __init__(self, opts):
        self.opts = opts

        self.probe_data = {}
        self.saved_config = None

        if self.opts.machine_config:
            with open(self.opts.machine_config) as mc:
                self.probe_data = self.saved_config = yaml.safe_load(mc)
        log.debug('Prober() init finished, data:{}'.format(self.saved_config))

    def probe_network(self, receiver):
        if self.opts.machine_config:
            observer = StoredDataObserver(
                self.saved_config['network'], receiver)
        else:
            observer = UdevObserver(receiver)
        return observer, observer.start()

    def get_storage(self, probe_types=None):
        ''' Load a StorageInfo class.  Probe if it's not present '''
        if 'storage' not in self.probe_data:
            log.debug('get_storage: no storage in probe_data, fetching')
            storage = Storage()
            results = storage.probe(probe_types=probe_types)
            self.probe_data['storage'] = results

        if self.opts.machine_config is not None and probe_types is not None:
            r = self.saved_config['storage'].copy()
            for k in self.saved_config['storage']:
                if k not in probe_types:
                    r[k] = {}
            return r
        return self.probe_data['storage']
