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

from subiquitycore.models.network import NetworkModel

log = logging.getLogger('subiquity.models.network')


class NetworkModel(NetworkModel):

    def __init__(self):
        super().__init__("subiquity", support_wlan=False)
        self.override_config = None

    def render_config(self):
        if self.override_config is not None:
            return self.override_config
        else:
            return super().render_config()

    def render(self):
        netplan = self.render_config()
        wifis = netplan['network'].pop('wifis', None)
        r = {
            'write_files': {
                'etc_netplan_installer': {
                    'path': 'etc/netplan/00-installer-config.yaml',
                    'content': self.stringify_config(netplan),
                    },
                'nonet': {
                    'path': ('etc/cloud/cloud.cfg.d/'
                             'subiquity-disable-cloudinit-networking.cfg'),
                    'content': 'network: {config: disabled}\n',
                    },
                },
            }
        if wifis is not None:
            netplan_wifi = {
                'network': {
                    'version': 2,
                    'wifis': wifis,
                    },
                }
            r['write_files']['etc_netplan_installer_wifi'] = {
                'path': 'etc/netplan/00-installer-config-wifi.yaml',
                'content': self.stringify_config(netplan_wifi),
                'permissions': '0600',
                }
        return r
