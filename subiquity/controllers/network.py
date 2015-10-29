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
from subiquity.controller import ControllerPolicy
from subiquity.models import NetworkModel
from subiquity.ui.views import (NetworkView,
                                NetworkSetDefaultRouteView,
                                NetworkConfigureInterfaceView,
                                NetworkConfigureIPv4InterfaceView)
from subiquity.ui.dummy import DummyView

from subiquity.curtin import curtin_write_network_actions

log = logging.getLogger("subiquity.controller.network")

class NetworkController(ControllerPolicy):
    def __init__(self, common):
        super().__init__(common)
        self.model = NetworkModel(self.prober, self.opts)

    def network(self):
        title = "Network connections"
        excerpt = ("Configure at least the main interface this server will "
                   "use to talk to other machines, and preferably provide "
                   "sufficient access for updates.")
        footer = ("Additional networking info here")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 20)
        self.ui.set_body(NetworkView(self.model, self.signal))

    def network_finish(self, actions):
        try:
            curtin_write_network_actions(actions)
        except (PermissionError, FileNotFoundError):
            log.exception('Failed to obtain write permission')
            self.signal.emit_signal('filesystem:error',
                                    'curtin_write_network_actions')
            return None

        self.signal.emit_signal('menu:filesystem:main')

    def set_default_route(self):
        self.ui.set_header("Default route")
        self.ui.set_body(NetworkSetDefaultRouteView(self.model,
                                                    self.signal))

    def network_configure_interface(self, iface):
        self.ui.set_header("Network interface {}".format(iface))
        self.ui.set_body(NetworkConfigureInterfaceView(self.model,
                                                       self.signal,
                                                       iface))

    def network_configure_ipv4_interface(self, iface):
        self.model.prev_signal = ('Back to configure interface menu',
                                  'network:configure-interface-menu',
                                  'network_configure_interface')
        self.ui.set_header("Network interface {} manual IPv4 "
                           "configuration".format(iface))
        self.ui.set_body(NetworkConfigureIPv4InterfaceView(self.model,
                                                           self.signal,
                                                           iface))

    def network_configure_ipv6_interface(self, iface):
        self.model.prev_signal = ('Back to configure interface menu',
                                  'network:configure-interface-menu',
                                  'network_configure_interface')
        self.ui.set_body(DummyView(self.signal))

    def bond_interfaces(self):
        self.ui.set_body(DummyView(self.signal))

    def install_network_driver(self):
        self.ui.set_body(DummyView(self.signal))
