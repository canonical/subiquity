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
import threading
import time

import netifaces
import yaml

from subiquitycore.models import NetworkModel
from subiquitycore.ui.views import (NetworkView,
                                    NetworkSetDefaultRouteView,
                                    NetworkBondInterfacesView,
                                    NetworkConfigureInterfaceView,
                                    NetworkConfigureIPv4InterfaceView)
from subiquitycore.ui.dummy import DummyView
from subiquitycore.controller import BaseController
from subiquitycore.utils import run_command
from subiquitycore.prober import Prober

log = logging.getLogger("subiquitycore.controller.network")


class NetworkObserver:

    def update_addresses_for_interface(self, interface, addresses):
        log.debug("updated interface %s %s", interface, addresses)

    def new_interface(self, interface, info):
        log.debug("new interface %s %s", interface, info)

    def remove_interface(self, interface):
        log.debug("remove interface %s", interface)


class NetworkWatcher:
    """A NetworkWatcher watches the network configuration.

    Methods will be called on the passed observer when a change is
    detected. The reason for doing the interface this was is that this
    should really work by subscribing to netlink events but that seems
    hard.
    """

    def __init__(self, observer):
        self.observer = observer
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.info = self._probe()
        threading.Thread(target=self._run).start()

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join()
            self.thread = None

    def _probe(self):
        NETDEV_IGNORED_IFACES = ['lo', 'bridge', 'tun', 'tap', 'dummy']
        class opts:
            machine_config = None
        prober = Prober(opts)
        network_devices = prober.get_network_devices()

        info = {}

        for iface in [iface for iface in network_devices.keys()
                      if iface not in NETDEV_IGNORED_IFACES]:
            ifinfo = prober.get_network_info(iface)
            info[iface] = ifinfo

        return info

    def _run(self):
        while 1:
            log.debug("watching...")
            new_info = self._probe()
            new_ifs = set(new_info)
            old_ifs = set(self.info)
            for new_if in new_ifs - old_ifs:
                self.observer.new_interface(new_if, new_info[new_if])
            for old_if in old_ifs - new_ifs:
                self.observer.remove_interface(old_if)
            for ifname in old_ifs & new_ifs:
                if self.info[ifname].ip != new_info[ifname].ip:
                    self.observer.update_addresses_for_interface(ifname, new_info[ifname].ip)
            self.info = new_info
            if not self.running:
                return
            time.sleep(1.0)


class NetworkController(BaseController):
    def __init__(self, common):
        super().__init__(common)
        self.model = NetworkModel(self.prober, self.opts)
        self.watcher = NetworkWatcher(NetworkObserver())
        self.watcher.start()

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

        online = True
        network_error = None

        if self.opts.dry_run:
            pass
        else:
            with open('/etc/netplan/01-console-conf.yaml', 'w') as w:
                w.write(yaml.dump(config))
            network_error = 'generate'
            ret = run_command(['/lib/netplan/generate'])
            if ret['status'] == 0:
                network_error = 'apply'
                ret = run_command(['netplan', 'apply'])
            if ret['status'] == 0:
                network_error = 'timeout'
                ret = run_command(['/lib/systemd/systemd-networkd-wait-online',
                                   '--timeout=30'])
            online = ( ret['status'] == 0 )

        if online:
            self.watcher.stop()
            self.signal.emit_signal('menu:identity:main')
        else:
            self.ui.frame.body.show_network_error(network_error)

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

