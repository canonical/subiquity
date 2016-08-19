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
import os

import netifaces
import yaml

from subiquitycore.async import Async
from subiquitycore.models import NetworkModel
from subiquitycore.ui.views import (NetworkView,
                                    NetworkSetDefaultRouteView,
                                    NetworkBondInterfacesView,
                                    NetworkConfigureInterfaceView,
                                    NetworkConfigureIPv4InterfaceView)
from subiquitycore.ui.dummy import DummyView
from subiquitycore.controller import BaseController
from subiquitycore.utils import run_command_start, run_command_summarize

log = logging.getLogger("subiquitycore.controller.network")



class CommandSequence:
    def __init__(self, cmds, controller):
        self.cmds = cmds
        self.controller = controller

    def run(self):
        self._run1()

    def _run1(self):
        self.stage, cmd = self.cmds[0]
        self.cmds = self.cmds[1:]
        self.controller.ui.frame.body.error.set_text("trying " + self.stage)
        log.debug('running %s for stage %s', cmd, self.stage)
        self.proc = run_command_start(cmd)
        self.pipe = self.controller.loop.watch_pipe(self._complete)
        Async.pool.submit(self._communicate)

    def _communicate(self):
        stdout, stderr = self.proc.communicate()
        self.result = run_command_summarize(self.proc, stdout, stderr)
        os.write(self.pipe, b'x')

    def _complete(self, ignored):
        if self.result['status'] != 0:
            self.controller.ui.frame.body.show_network_error(self.stage)
        elif len(self.cmds) == 0:
            self.controller.signal.emit_signal('menu:identity:main')
        else:
            self._run1()


class NetworkController(BaseController):
    def __init__(self, common):
        super().__init__(common)
        self.model = NetworkModel(self.prober, self.opts)

    def network(self):
        title = "Network connections"
        excerpt = ("Configure at least the main interface this server will "
                   "use to talk to the store.")
        footer = ("Additional networking info here")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 20)
        self.ui.set_body(NetworkView(self.model, self.signal))

    def network_finish(self, config):
        log.debug("network config: \n%s", yaml.dump(config, default_flow_style=False))

        self.ui.frame.body.error.set_text("trying")

        if self.opts.dry_run:
            if hasattr(self, 'tried_once'):
                cmds = [
                    ('one', ['sleep', '1']),
                    ('two', ['sleep', '1']),
                    ('three', ['sleep', '1']),
                    ]
            else:
                self.tried_once = True
                cmds = [
                    ('one', ['sleep', '1']),
                    ('two', ['sleep', '1']),
                    ('three', ['false']),
                    ('four', ['sleep 1']),
                    ]
        else:
            with open('/etc/netplan/01-console-conf.yaml', 'w') as w:
                w.write(yaml.dump(config))
            cmds = [
                ('generate', ['/lib/netplan/generate']),
                ('apply', ['netplan', 'apply']),
                ('timeout', ['/lib/systemd/systemd-networkd-wait-online', '--timeout=30']),
                ]
        CommandSequence(cmds, self).run()

    def set_default_v4_route(self):
        self.ui.set_header("Default route")
        self.ui.set_body(NetworkSetDefaultRouteView(self.model,
                                                    netifaces.AF_INET,
                                                    self.signal))

    def set_default_v6_route(self):
        self.ui.set_header("Default route")
        self.ui.set_body(NetworkSetDefaultRouteView(self.model,
                                                    netifaces.AF_INET6,
                                                    self.signal))

    def bond_interfaces(self):
        self.ui.set_header("Bond interfaces")
        self.ui.set_body(NetworkBondInterfacesView(self.model,
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

    def install_network_driver(self):
        self.ui.set_body(DummyView(self.signal))

