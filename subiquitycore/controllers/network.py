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
import queue

import netifaces
import yaml

from subiquitycore.async import Async
from subiquitycore.models import NetworkModel
from subiquitycore.ui.views import (NetworkView,
                                    NetworkSetDefaultRouteView,
                                    NetworkBondInterfacesView,
                                    NetworkConfigureInterfaceView,
                                    NetworkConfigureIPv4InterfaceView)
from subiquitycore.ui.views.network import ApplyingConfigWidget
from subiquitycore.ui.dummy import DummyView
from subiquitycore.controller import BaseController
from subiquitycore.utils import run_command_start, run_command_summarize

log = logging.getLogger("subiquitycore.controller.network")


class CommandSequence:
    def __init__(self, loop, cmds, watcher):
        self.loop = loop
        self.cmds = cmds
        self.watcher = watcher
        self.canceled = False
        self.stage = None
        self.queue = queue.Queue()

    def run(self):
        self._run1()

    def cancel(self):
        log.debug('canceling stage %s', self.stage)
        self.canceled = True
        try:
            self.proc.terminate()
        except ProcessLookupError:
            pass

    def _run1(self):
        self.stage, cmd = self.cmds[0]
        self.cmds = self.cmds[1:]
        log.debug('running %s for stage %s', cmd, self.stage)
        self.proc = run_command_start(cmd)
        self.pipe = self.loop.watch_pipe(self._thread_callback)
        Async.pool.submit(self._communicate)

    def _communicate(self):
        stdout, stderr = self.proc.communicate()
        result = run_command_summarize(self.proc, stdout, stderr)
        self.call_from_thread(self._complete, result)

    def call_from_thread(self, func, *args):
        self.queue.put((func, args))
        os.write(self.pipe, b'x')

    def _thread_callback(self, ignored):
        func, args = self.queue.get()
        func(*args)

    def _complete(self, result):
        if self.canceled:
            return
        if result['status'] != 0:
            self.watcher.cmd_error(self.stage)
            return
        self.watcher.cmd_complete(self.stage)
        if len(self.cmds) == 0:
            self.watcher.cmd_finished()
        else:
            self._run1()


class NetworkController(BaseController):
    def __init__(self, common):
        super().__init__(common)
        self.model = NetworkModel(self.prober, self.opts)

    def network(self):
        # The network signal is the one that is called when we enter
        # the network configuration from the preceding or following
        # screen. We clear any existing state, probe for the current
        # state and then invoke the 'start' signal, which is what the
        # sub screens will return to, so that the network state does
        # not get re-probed when they return, which would throw away
        # any configuration made in the sub-screen!
        self.model.reset()
        log.info("probing for network devices")
        self.model.probe_network()
        self.signal.emit_signal('menu:network:main:start')

    def start(self):
        title = "Network connections"
        excerpt = ("Configure at least the main interface this server will "
                   "use to talk to the store.")
        footer = ("Additional networking info here")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 20)
        self.ui.set_body(NetworkView(self.model, self.signal))

    def network_finish(self, config):
        log.debug("network config: \n%s", yaml.dump(config, default_flow_style=False))

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

        def cancel():
            self.cs.cancel()
            self.cmd_error('canceled')
        self.acw = ApplyingConfigWidget(len(cmds), cancel)
        self.ui.frame.body.show_overlay(self.acw)

        self.cs = CommandSequence(self.loop, cmds, self)
        self.cs.run()

    def cmd_complete(self, stage):
        self.acw.advance()

    def cmd_error(self, stage):
        self.ui.frame.body.remove_overlay(self.acw)
        self.ui.frame.body.show_network_error(stage)

    def cmd_finished(self):
        self.signal.emit_signal('menu:identity:main')

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

