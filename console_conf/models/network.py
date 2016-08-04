# Copyright 2016 Canonical, Ltd.
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

from subiquitycore.model import BaseModel
from console_conf.models import NetworkConfig


NETDEV_IGNORED_IFACES = ['lo', 'bridge', 'tun', 'tap']
log = logging.getLogger('subiquitycore.models.network')


class NetworkModel(BaseModel):
    """ Model representing network interfaces
    """
    base_signal = 'menu:network:main'
    signals = [
        ('Network main view',
         base_signal,
         'network'),
        ('Network finish',
         'network:finish',
         'network_finish'),
        ## ('Network configure interface',
        ##  base_signal + ':configure-interface',
        ##  'network_configure_interface'),
        ## ('Network configure ipv4 interface',
        ##  base_signal + ':configure-ipv4-interface',
        ##  'network_configure_ipv4_interface')
    ]

    additional_options = [
    ##     ('Set default route',
    ##      base_signal + ':set-default-route',
    ##      'set_default_route'),
    ##     ('Bond interfaces',
    ##      base_signal + ':bond-interfaces',
    ##      'bond_interfaces'),
    ##     # ('Install network driver',
    ##     #  'network:install-network-driver',
    ##     #  'install_network_driver')
    ]

    def __init__(self, probe_data, opts):
        self._probe_data = probe_data
        self.opts = opts
        self.reset()

    def get_signal_by_name(self, selection):
        for x, y, z in self.get_signals():
            if x == selection:
                return y

    def get_signals(self):
        return self.signals + self.additional_options

    def get_menu(self):
        return self.additional_options

    def reset(self):
        self.config = NetworkConfig.from_probe_data(self._probe_data)
