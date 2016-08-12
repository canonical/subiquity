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

import netifaces
import yaml

from subiquitycore.controller import BaseController
from subiquitycore.utils import run_command

from console_conf.models import NetworkModel
from console_conf.ui.views import NetworkView, NetworkConfigureInterfaceView

log = logging.getLogger("subiquitycore.controller.network")


class NetworkController(BaseController):
    def __init__(self, common):
        super().__init__(common)
        self.prober._probe_network()
        self.model = NetworkModel(self.prober.probe_data, self.opts)

    def network(self):
        title = "Network connections"
        excerpt = ("Configure at least the main interface this server will "
                   "use to talk to the store.")
        footer = ("Additional networking info here")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 20)
        self.ui.set_body(NetworkView(self.model, self.signal))

    def network_finish(self, config):
        log.debug("network config: \n%s", yaml.dump(config))
        #self.ui.frame.body = 
        if self.opts.dry_run:
            pass
        else:
            with open('/etc/netplan/01-console-conf.yaml', 'w') as w:
                w.write(yaml.dump(config))
            run_command(['systemctl', 'restart', 'systemd-networkd'])
            while 'default' not in netifaces.gateways():
                time.sleep(0.1)
        self.signal.emit_signal('menu:identity:main')

    def network_configure_interface(self, interface):
        self.ui.set_header("Network interface {}".format(interface))
        self.ui.set_body(NetworkConfigureInterfaceView(
            self.model, self.signal, self.model.config.ethernets[interface]))
