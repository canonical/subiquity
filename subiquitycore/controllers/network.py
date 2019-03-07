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
import subprocess

import yaml

from probert.network import IFF_UP, NetworkEventReceiver

from subiquitycore.models.network import BondParameters, sanitize_config
from subiquitycore.tasksequence import (
    BackgroundTask,
    BackgroundProcess,
    CancelableTask,
    PythonSleep,
    TaskSequence,
    TaskWatcher,
    )
from subiquitycore.ui.views.network import (
    ApplyingConfigWidget,
    NetworkView,
    )
from subiquitycore.controller import BaseController
from subiquitycore.utils import run_command
from subiquitycore.file_util import write_file
from subiquitycore import netplan

log = logging.getLogger("subiquitycore.controller.network")


class DownNetworkDevices(BackgroundTask):

    def __init__(self, rtlistener, devs_to_down, devs_to_delete):
        self.rtlistener = rtlistener
        self.devs_to_down = devs_to_down
        self.devs_to_delete = devs_to_delete

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
        for dev in self.devs_to_delete:
            # XXX would be nicer to do this via rtlistener eventually.
            log.debug('deleting %s', dev.name)
            cmd = ['ip', 'link', 'delete', 'dev', dev.name]
            try:
                run_command(cmd, check=True)
            except subprocess.CalledProcessError as cp:
                log.info("deleting %s failed with %r", dev.name, cp.stderr)

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
        self.view = None
        self.default_route_waiter = None
        self.default_routes = set()

    def new_link(self, ifindex, link):
        netdev = self.model.new_link(ifindex, link)
        if self.view is not None and netdev is not None:
            self.view.new_link(netdev)

    def del_link(self, ifindex):
        netdev = self.model.del_link(ifindex)
        if ifindex in self.default_routes:
            self.default_routes.remove(ifindex)
        if self.view is not None and netdev is not None:
            self.view.del_link(netdev)

    def update_link(self, ifindex):
        netdev = self.model.update_link(ifindex)
        if self.view is not None and netdev is not None:
            self.view.update_link(netdev)

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
                self.default_route_waiter = None
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
        self._done_by_action = False

    def start(self):
        self._observer_handles = []
        self.observer, self._observer_fds = (
            self.prober.probe_network(self.network_event_receiver))
        self.start_watching()

    def stop_watching(self):
        for handle in self._observer_handles:
            self.loop.remove_watch_file(handle)
        self._observer_handles = []

    def start_watching(self):
        if self._observer_handles:
            return
        self._observer_handles = [
            self.loop.watch_file(fd, partial(self._data_ready, fd))
            for fd in self._observer_fds]

    def _data_ready(self, fd):
        cp = run_command(['udevadm', 'settle', '-t', '0'])
        if cp.returncode != 0:
            log.debug("waiting 0.1 to let udev event queue settle")
            self.stop_watching()
            self.loop.set_alarm_in(0.1, lambda loop, ud: self.start_watching())
            return
        self.observer.data_ready(fd)
        v = self.ui.frame.body
        if hasattr(v, 'refresh_model_inputs'):
            v.refresh_model_inputs()

    def start_scan(self, dev):
        self.observer.trigger_scan(dev.ifindex)

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def _action_get(self, id):
        dev_spec = id[0].split()
        dev = None
        if dev_spec[0] == "interface":
            if dev_spec[1] == "index":
                dev = self.model.get_all_netdevs()[int(dev_spec[2])]
            elif dev_spec[1] == "name":
                dev = self.model.get_netdev_by_name(dev_spec[2])
        if dev is None:
            raise Exception("could not resolve {}".format(id))
        if len(id) > 1:
            part, index = id[1].split()
            if part == "part":
                return dev.partitions()[int(index)]
        else:
            return dev
        raise Exception("could not resolve {}".format(id))

    def _action_clean_devices(self, devices):
        return [self._action_get(device) for device in devices]

    def _answers_action(self, action):
        from subiquitycore.ui.stretchy import StretchyOverlay
        log.debug("_answers_action %r", action)
        if 'obj' in action:
            obj = self._action_get(action['obj'])
            meth = getattr(
                self.ui.frame.body,
                "_action_{}".format(action['action']))
            meth(obj)
            yield
            body = self.ui.frame.body._w
            if not isinstance(body, StretchyOverlay):
                return
            for k, v in action.items():
                if not k.endswith('data'):
                    continue
                form_name = "form"
                submit_key = "submit"
                if '-' in k:
                    prefix = k.split('-')[0]
                    form_name = prefix + "_form"
                    submit_key = prefix + "-submit"
                yield from self._enter_form_data(
                    getattr(body.stretchy, form_name),
                    v,
                    action.get(submit_key, True))
        elif action['action'] == 'create-bond':
            self.ui.frame.body._create_bond()
            yield
            body = self.ui.frame.body._w
            yield from self._enter_form_data(
                body.stretchy.form,
                action['data'],
                action.get("submit", True))
        elif action['action'] == 'done':
            self._done_by_action = True
            self.ui.frame.body.done()
        else:
            raise Exception("could not process action {}".format(action))

    def default(self):
        view = NetworkView(self.model, self)
        self.network_event_receiver.view = view
        self.ui.set_body(view)
        if self.answers.get('accept-default', False):
            self.network_finish(self.model.render())
        elif self.answers.get('actions', False):
            self._run_iterator(self._run_actions(self.answers['actions']))

    @property
    def netplan_path(self):
        if self.opts.project == "subiquity":
            netplan_config_file_name = '00-installer-config.yaml'
        else:
            netplan_config_file_name = '00-snapd-config.yaml'
        return os.path.join(self.root, 'etc/netplan', netplan_config_file_name)

    def add_vlan(self, device, vlan):
        return self.model.new_vlan(device, vlan)

    def add_or_update_bond(self, existing, result):
        mode = result['mode']
        params = {
            'mode': mode,
            }
        if mode in BondParameters.supports_xmit_hash_policy:
            params['transmit-hash-policy'] = result['xmit_hash_policy']
        if mode in BondParameters.supports_lacp_rate:
            params['lacp-rate'] = result['lacp_rate']
        for device in result['devices']:
            device.config = {}
        interfaces = [d.name for d in result['devices']]
        if existing is None:
            return self.model.new_bond(result['name'], interfaces, params)
        else:
            existing.config['interfaces'] = interfaces
            existing.config['parameters'] = params
            existing.name = result['name']
            return existing

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
            yaml.dump(config, default_flow_style=False))), omode="w")

        self.model.parse_netplan_configs(self.root)
        if self.opts.dry_run:
            delay = 0.1/self.scale_factor
            tasks = [
                ('one', BackgroundProcess(['sleep', str(delay)])),
                ('two', PythonSleep(delay)),
                ('three', BackgroundProcess(['sleep', str(delay)])),
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
            devs_to_delete = []
            devs_to_down = []
            for dev in self.model.get_all_netdevs(include_deleted=True):
                if dev.info is None:
                    continue
                devcfg = self.model.config.config_for_device(dev.info)
                if dev.is_virtual:
                    devs_to_delete.append(dev)
                elif dev.config != devcfg:
                    devs_to_down.append(dev)
            tasks = []
            if devs_to_down or devs_to_delete:
                tasks.extend([
                    ('stop-networkd',
                     BackgroundProcess(['systemctl',
                                        'stop', 'systemd-networkd.service'])),
                    ('down',
                     DownNetworkDevices(self.observer.rtlistener,
                                        devs_to_down, devs_to_delete)),
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
        if self.answers.get('accept-default', False) or self._done_by_action:
            self.network_finish(self.model.render())

    def tasks_finished(self):
        self.signal.emit_signal('network-config-written', self.netplan_path)
        self.loop.set_alarm_in(
            0.0, lambda loop, ud: self.signal.emit_signal('next-screen'))
