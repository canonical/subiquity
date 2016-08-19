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
import subprocess
import sys

import netifaces
import yaml

from probert.network import NetworkInfo

from subiquitycore.models import NetworkModel
from subiquitycore.ui.views import (NetworkView,
                                    NetworkSetDefaultRouteView,
                                    NetworkBondInterfacesView,
                                    NetworkConfigureInterfaceView,
                                    NetworkConfigureIPv4InterfaceView)
from subiquitycore.ui.dummy import DummyView
from subiquitycore.controller import BaseController
from subiquitycore.utils import run_command

log = logging.getLogger("subiquitycore.controller.network")


class NetworkController(BaseController):
    def __init__(self, common):
        super().__init__(common)
        self.model = NetworkModel(self.prober, self.opts)
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(os.path.dirname(__file__), 'netwatch.py')],
            bufsize=0, stdout=subprocess.PIPE)
        self.watch_handle = self.loop.watch_file(self.proc.stdout, self.output)
        self.buf = b''

    def output(self):
        self.buf += self.proc.stdout.read(1024)
        if b'\0' in self.buf:
            lines = self.buf.split(b'\0')
            self.buf = lines[-1]
            for line in lines[:-1]:
                update = yaml.safe_load(line.decode('utf-8'))
                ifname = update['ifname']
                action = update['action']
                if action == 'new_interface':
                    log.debug("new %s %s", ifname, update['data'])
                    self.model.new_interface(NetworkInfo({ifname: update['data']}))
                elif action == 'update_interface':
                    log.debug("update %s %s", ifname, update['data'])
                    self.model.new_interface(NetworkInfo({ifname: update['data']}))
                elif action == 'remove_interface':
                    log.debug("remove %s", ifname)
                    if ifname in self.model.devices:
                        del self.model.devices[ifname]
                    if ifname in self.model.info:
                        del self.model.info[ifname]
                if isinstance(self.ui.frame.body, NetworkView):
                    self.ui.frame.body.refresh_model_inputs()

    def network(self):
        title = "Network connections"
        excerpt = ("Configure at least the main interface this server will "
                   "use to talk to the store.")
        footer = ("Additional networking info here")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 20)
        self.ui.set_body(NetworkView(self.model, self.signal))

    def _run(self, last_stage, results, cmds):
        log.debug('_run called with %s', cmds)
        if results['status'] != 0:
            self.ui.frame.body.show_network_error(last_stage)
            return
        if len(cmds) == 0:
            self.signal.emit_signal('menu:identity:main')
            return
        stage, cmd = cmds[0]
        rest = cmds[1:]
        self.ui.frame.body.error.set_text("trying " + stage)
        log.debug('running %s for stage %s', cmd, stage)
        results = []
        def complete(ignored):
            self._run(stage, results[0], rest)
            #os.close(pipe)
        pipe = self.loop.watch_pipe(complete)
        import threading
        def t():
            results.append(run_command(cmd))
            log.debug('%s completed, result %s', cmd, results[0])
            os.write(pipe, b'x')
        threading.Thread(target=t).start()

    def run_commands(self, cmds):
        self._run('', {'status':0}, cmds)

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
        self.run_commands(cmds)

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

