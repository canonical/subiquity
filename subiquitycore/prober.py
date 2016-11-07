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
import os
from probert.storage import (Storage,
                             StorageInfo)

log = logging.getLogger('subiquitycore.prober')


class ProberException(Exception):
    '''Base Prober Exception'''
    pass


class Prober():
    def __init__(self, opts):
        self.opts = opts
        self.probe_data = {}

        if self.opts.machine_config:
            log.debug('User specified machine_config: {}'.format(
                      self.opts.machine_config))
            if os.path.exists(self.opts.machine_config):
                self.probe_data = \
                    self._load_machine_config(self.opts.machine_config)
        log.debug('Prober() init finished, data:{}'.format(self.probe_data))

    def _load_machine_config(self, machine_config):
        with open(machine_config) as mc:
            try:
                data = yaml.safe_load(mc)
            except (UnicodeDecodeError, yaml.reader.ReaderError):
                err = 'Failed to parse machine config'
                log.exception(err)
                raise ProberException(err)

        return data

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
