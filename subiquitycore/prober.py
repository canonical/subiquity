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
import time
import yaml

from probert.network import (
    StoredDataObserver,
    UdevObserver,
    )

log = logging.getLogger('subiquitycore.prober')


class Prober():
    def __init__(self, machine_config, debug_flags):
        self.saved_config = None
        if machine_config:
            with open(machine_config) as mc:
                self.saved_config = yaml.safe_load(mc)
        self.debug_flags = debug_flags
        log.debug('Prober() init finished, data:{}'.format(self.saved_config))

    def probe_network(self, receiver):
        if self.saved_config is not None:
            observer = StoredDataObserver(
                self.saved_config['network'], receiver)
        else:
            observer = UdevObserver(receiver)
        return observer, observer.start()

    def get_storage(self, probe_types=None):
        if self.saved_config is not None:
            flag = 'bpfail-full'
            if probe_types is not None:
                flag = 'bpfail-restricted'
            if flag in self.debug_flags:
                time.sleep(2)
                1/0
            r = self.saved_config['storage'].copy()
            if probe_types is not None:
                for k in self.saved_config['storage']:
                    if k not in probe_types:
                        r[k] = {}
            return r
        from probert.storage import Storage
        return Storage().probe(probe_types=probe_types)
