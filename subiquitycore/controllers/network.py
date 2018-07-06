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

from functools import partial
import logging
import os
import select
import socket
import subprocess

import yaml

from probert.network import IFF_UP, NetworkEventReceiver

from subiquitycore.models.network import sanitize_config
from subiquitycore.tasksequence import (
    BackgroundTask,
    BackgroundProcess,
    CancelableTask,
    PythonSleep,
    TaskSequence,
    TaskWatcher,
    )
from subiquitycore.ui.views import (NetworkView,
                                    NetworkSetDefaultRouteView,
                                    NetworkBondInterfacesView)
from subiquitycore.ui.views.network import ApplyingConfigWidget
from subiquitycore.controller import BaseController
from subiquitycore.utils import run_command
from subiquitycore.file_util import write_file
from subiquitycore import netplan

log = logging.getLogger("subiquitycore.controller.network")


class DownNetworkDevices(BackgroundTask):

    def __init__(self, rtlistener, devs_to_down):
        self.rtlistener = rtlistener
        self.devs_to_down = devs_to_down

    def __repr__(self):
        return 'DownNetworkDevices(%s)' % ([dev.name for dev in
                                            self.devs_to_down],)

    def start(self):
        for dev in self.devs_to_down:
            try:
                log.debug('downing %s', dev.name)
                self.rtlistener.unset_link_flags(dev.ifindex, IFF_UP)
            except RuntimeError:
                # We don't actually care very much about this
                log.exception('unset_link_flags failed for %s', dev.name)

    def _bg_run(self):
        return True

    def end(self, observer, fut):
        if fut.result():
            observer.task_succeeded()
        else:
            observer.task_failed()


class WaitForDefaultRouteTask(CancelableTask):

    def __init__(self, timeout, event_receiver):
        self.timeout = timeout
        self.event_receiver = event_receiver

    def __repr__(self):
        return 'WaitForDefaultRouteTask(%r)' % (self.timeout,)

    def got_route(self):
        os.write(self.success_w, b'x')

    def start(self):
        self.fail_r, self.fail_w = os.pipe()
        self.success_r, self.success_w = os.pipe()
        self.event_receiver.add_default_route_waiter(self.got_route)

    def _bg_run(self):
        try:
            r, _, _ = select.select([self.fail_r, self.success_r], [], [],
                                    self.timeout)
            return self.success_r in r
        finally:
            os.close(self.fail_r)
            os.close(self.fail_w)
            os.close(self.success_r)
            os.close(self.success_w)

    def end(self, observer, fut):
        if fut.result():
            observer.task_succeeded()
        else:
            observer.task_failed('timeout')

    def cancel(self):
        os.write(self.fail_w, b'x')


class SubiquityNetworkEventReceiver(NetworkEventReceiver):
    def __init__(self, model):
        self.model = model
        self.default_route_waiter = None
        self.default_routes = set()

    def new_link(self, ifindex, link):
        self.model.new_link(ifindex, link)

    def del_link(self, ifindex):
        self.model.del_link(ifindex)
        if ifindex in self.default_routes:
            self.default_routes.remove(ifindex)

    def update_link(self, ifindex):
        self.model.update_link(ifindex)

    def route_change(self, action, data):
        super().route_change(action, data)
        if data['dst'] != 'default':
            return
        if data['table'] != 254:
            return
        ifindex = data['ifindex']
        if action == "NEW" or action == "CHANGE":
            self.default_routes.add(ifindex)
            if self.default_route_waiter:
                self.default_route_waiter()
        elif action == "DEL" and ifindex in self.default_routes:
            self.default_routes.remove(ifindex)
        log.debug('default routes %s', self.default_routes)

    def add_default_route_waiter(self, waiter):
        if self.default_routes:
            waiter()
        else:
            self.default_route_waiter = waiter


default_netplan = '''
network:
  version: 2
  ethernets:
    "en*":
       addresses:
         - 10.0.2.15/24
       gateway4: 10.0.2.2
       nameservers:
         addresses:
           - 8.8.8.8
           - 8.4.8.4
         search:
           - foo
           - bar
    "eth*":
       dhcp4: true
  wifis:
    "wl*":
       dhcp4: true
       access-points:
         "some-ap":
            password: password
'''


class NetworkController(BaseController, TaskWatcher):
    signals = [
        ('menu:network:main:set-default-v4-route',     'set_default_v4_route'),
        ('menu:network:main:set-default-v6-route',     'set_default_v6_route'),
    ]

    root = "/"

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.network
        self.answers = self.all_answers.get("Network", {})
        if self.opts.dry_run:
            self.root = os.path.abspath(".subiquity")
            self.tried_once = False
            netplan_path = self.netplan_path
            netplan_dir = os.path.dirname(netplan_path)
            if os.path.exists(netplan_dir):
                import shutil
                shutil.rmtree(netplan_dir)
            os.makedirs(netplan_dir)
            with open(netplan_path, 'w') as fp:
                fp.write(default_netplan)
        self.model.parse_netplan_configs(self.root)

        self.network_event_receiver = SubiquityNetworkEventReceiver(self.model)
        self.observer, fds = (
            self.prober.probe_network(self.network_event_receiver))
        for fd in fds:
            self.loop.watch_file(fd, partial(self._data_ready, fd))

    def _data_ready(self, fd):
        cp = run_command(['udevadm', 'settle', '-t', '0'])
        if cp.returncode != 0:
            log.debug("waiting 0.1 to let udev event queue settle")
            self.loop.set_alarm_in(0.1, lambda loop, ud: self._data_ready(fd))
            return
        self.observer.data_ready(fd)
        v = self.ui.frame.body
        if hasattr(v, 'refresh_model_inputs'):
            v.refresh_model_inputs()

    def start_scan(self, dev):
        self.observer.trigger_scan(dev.ifindex)

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def default(self):
        self.ui.set_body(NetworkView(self.model, self))
        if self.answers.get('accept-default', False):
            self.network_finish(self.model.render())

    @property
    def netplan_path(self):
        if self.opts.project == "subiquity":
            netplan_config_file_name = '00-installer-config.yaml'
        else:
            netplan_config_file_name = '00-snapd-config.yaml'
        return os.path.join(self.root, 'etc/netplan', netplan_config_file_name)

    def add_vlan(self, device, vlan):
        cmd = ['ip', 'link', 'add', 'name', '%s.%s' % (device.name, vlan),
               'link', device.name, 'type', 'vlan', 'id', str(vlan)]
        try:
            run_command(cmd, check=True)
        except subprocess.CalledProcessError:
            self.ui.frame.body.show_network_error('add-vlan')

    def rm_virtual_interface(self, device):
        cmd = ['ip', 'link', 'delete', 'dev', device.name]
        try:
            run_command(cmd, check=True)
        except subprocess.CalledProcessError:
            self.ui.frame.body.show_network_error('rm-dev')

    def network_finish(self, config):
        log.debug("network config: \n%s",
                  yaml.dump(sanitize_config(config), default_flow_style=False))

        for p in netplan.configs_in_root(self.root, masked=True):
            if p == self.netplan_path:
                continue
            os.rename(p, p + ".dist-" + self.opts.project)

        write_file(self.netplan_path, '\n'.join((
            ("# This is the network config written by '%s'" %
             self.opts.project),
            yaml.dump(config))), omode="w")

        self.model.parse_netplan_configs(self.root)
        if self.opts.dry_run:
            tasks = [
                ('one', BackgroundProcess(['sleep', '0.1'])),
                ('two', PythonSleep(0.1)),
                ('three', BackgroundProcess(['sleep', '0.1'])),
                ]
            if os.path.exists('/lib/netplan/generate'):
                # If netplan appears to be installed, run generate to at
                # least test that what we wrote is acceptable to netplan.
                tasks.append(('generate',
                              BackgroundProcess(['netplan', 'generate',
                                                 '--root', self.root])))
            if not self.tried_once:
                tasks.append(
                    ('timeout',
                     WaitForDefaultRouteTask(3, self.network_event_receiver))
                )
                tasks.append(('fail', BackgroundProcess(['false'])))
                self.tried_once = True
        else:
            devs_to_down = []
            for dev in self.model.get_all_netdevs():
                devcfg = self.model.config.config_for_device(dev._net_info)
                if dev._configuration != devcfg:
                    devs_to_down.append(dev)
            tasks = []
            if devs_to_down:
                tasks.extend([
                    ('stop-networkd',
                     BackgroundProcess(['systemctl',
                                        'stop', 'systemd-networkd.service'])),
                    ('down',
                     DownNetworkDevices(self.observer.rtlistener,
                                        devs_to_down)),
                    ])
            tasks.extend([
                ('apply', BackgroundProcess(['netplan', 'apply'])),
                ('timeout',
                 WaitForDefaultRouteTask(30, self.network_event_receiver)),
                ])

        def cancel():
            self.cs.cancel()
            self.task_error('canceled')
        self.acw = ApplyingConfigWidget(len(tasks), cancel)
        self.ui.frame.body.show_overlay(self.acw, min_width=60)

        self.cs = TaskSequence(self.run_in_bg, tasks, self)
        self.cs.run()

    def task_complete(self, stage):
        self.acw.advance()

    def task_error(self, stage, info=None):
        self.ui.frame.body.remove_overlay()
        self.ui.frame.body.show_network_error(stage, info)
        if self.answers.get('accept-default', False):
            self.network_finish(self.model.render())

    def tasks_finished(self):
        self.signal.emit_signal('network-config-written', self.netplan_path)
        self.signal.emit_signal('next-screen')

    def set_default_v4_route(self):
        self.ui.set_header("Default route")
        self.ui.set_body(
            NetworkSetDefaultRouteView(self.model, socket.AF_INET, self))

    def set_default_v6_route(self):
        self.ui.set_header("Default route")
        self.ui.set_body(
            NetworkSetDefaultRouteView(self.model, socket.AF_INET6, self))

    def bond_interfaces(self):
        self.ui.set_body(NetworkBondInterfacesView(self.model, self))
