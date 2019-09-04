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
import subprocess

import yaml

from probert.network import IFF_UP, NetworkEventReceiver

from subiquitycore.models.network import BondParameters, sanitize_config
from subiquitycore.tasksequence import (
    BackgroundTask,
    BackgroundProcess,
    PythonSleep,
    TaskSequence,
    TaskWatcher,
    )
from subiquitycore.ui.views.network import (
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
        return 'DownNetworkDevices({}, {})'.format(
            [dev.name for dev in self.devs_to_down],
            [dev.name for dev in self.devs_to_delete],
            )

    def start(self):
        pass

    def _bg_run(self):
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

    def end(self, observer, fut):
        observer.task_succeeded()


class ApplyWatcher(TaskWatcher):
    def __init__(self, view, controller):
        self.view = view
        self.controller = controller

    def task_complete(self, stage):
        pass

    def tasks_finished(self):
        self.view.hide_apply_spinner()
        if self.controller.answers.get('accept-default', False):
            self.controller.done()
        elif self.controller.answers.get('actions', False):
            self.controller._run_iterator(
                self.controller._run_actions(
                    self.controller.answers['actions']))

    def task_error(self, stage, info):
        self.view.show_network_error(stage, info)


class SubiquityNetworkEventReceiver(NetworkEventReceiver):
    def __init__(self, model):
        self.model = model
        self.view = None
        self.default_route_watchers = []
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
        if netdev is None:
            return
        if not (netdev.info.flags & IFF_UP) and ifindex in self.default_routes:
            self.default_routes.remove(ifindex)
            for watcher in self.default_route_watchers:
                watcher(self.default_routes)
        if self.view is not None:
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
        elif action == "DEL" and ifindex in self.default_routes:
            self.default_routes.remove(ifindex)
        for watcher in self.default_route_watchers:
            watcher(self.default_routes)
        log.debug('default routes %s', self.default_routes)

    def add_default_route_watcher(self, watcher):
        self.default_route_watchers.append(watcher)
        watcher(self.default_routes)

    def remove_default_route_watcher(self, watcher):
        if watcher in self.default_route_watchers:
            self.default_route_watchers.remove(watcher)


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


class NetworkController(BaseController):

    root = "/"

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model.network
        self.view = None
        self.view_shown = False
        self.dhcp_check_handle = None
        if self.opts.dry_run:
            self.root = os.path.abspath(".subiquity")
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
        self.network_event_receiver.add_default_route_watcher(
            self.route_watcher)

    def route_watcher(self, routes):
        if routes:
            self.signal.emit_signal('network-change')

    def start(self):
        self._observer_handles = []
        self.observer, self._observer_fds = (
            self.app.prober.probe_network(self.network_event_receiver))
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
        v = self.ui.body
        if hasattr(v, 'refresh_model_inputs'):
            v.refresh_model_inputs()

    def start_scan(self, dev):
        self.observer.trigger_scan(dev.ifindex)

    def done(self):
        log.debug("NetworkController.done next-screen")
        self.model.has_network = bool(
            self.network_event_receiver.default_routes)
        self.signal.emit_signal('next-screen')

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
                self.ui.body,
                "_action_{}".format(action['action']))
            meth(obj)
            yield
            body = self.ui.body._w
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
            self.ui.body._create_bond()
            yield
            body = self.ui.body._w
            yield from self._enter_form_data(
                body.stretchy.form,
                action['data'],
                action.get("submit", True))
        elif action['action'] == 'done':
            self.ui.body.done()
        else:
            raise Exception("could not process action {}".format(action))

    def update_initial_configs(self):
        # Any device that does not have a (global) address by the time
        # we get to the network screen is marked as disabled, with an
        # explanation.
        log.debug("updating initial NIC config")
        for dev in self.model.get_all_netdevs():
            has_global_address = False
            if dev.info is None or not dev.config:
                continue
            for a in dev.info.addresses.values():
                if a.scope == "global":
                    has_global_address = True
                    break
            if not has_global_address:
                dev.remove_ip_networks_for_version(4)
                dev.remove_ip_networks_for_version(6)
                log.debug("disabling %s", dev.name)
                dev.disabled_reason = _("autoconfiguration failed")

    def check_dchp_results(self, device_versions):
        log.debug('check_dchp_results for %s', device_versions)
        for dev, v in device_versions:
            if not dev.dhcp_addresses()[v]:
                dev.set_dhcp_state(v, "TIMEDOUT")
                self.network_event_receiver.update_link(dev.ifindex)

    def start_ui(self):
        if not self.view_shown:
            self.update_initial_configs()
        self.view = NetworkView(self.model, self)
        if not self.view_shown:
            self.apply_config(silent=True)
            self.view_shown = True
        self.network_event_receiver.view = self.view
        self.ui.set_body(self.view)

    def end_ui(self):
        self.view = self.network_event_receiver.view = None

    @property
    def netplan_path(self):
        if self.opts.project == "subiquity":
            netplan_config_file_name = '00-installer-config.yaml'
        else:
            netplan_config_file_name = '00-snapd-config.yaml'
        return os.path.join(self.root, 'etc/netplan', netplan_config_file_name)

    def apply_config(self, silent=False):
        log.debug("apply_config silent=%s", silent)
        if self.dhcp_check_handle is not None:
            self.loop.remove_alarm(self.dhcp_check_handle)
            self.dhcp_check_handle = None

        config = self.model.render()

        devs_to_delete = []
        devs_to_down = []
        dhcp_device_versions = []
        for dev in self.model.get_all_netdevs(include_deleted=True):
            for v in 4, 6:
                if dev.dhcp_enabled(v):
                    if not silent:
                        dev.set_dhcp_state(v, "PENDING")
                        self.network_event_receiver.update_link(dev.ifindex)
                    else:
                        dev.set_dhcp_state(v, "RECONFIGURE")
                    dhcp_device_versions.append((dev, v))
            if dev.info is None:
                continue
            if dev.is_virtual:
                devs_to_delete.append(dev)
                continue
            if dev.config != self.model.config.config_for_device(dev.info):
                devs_to_down.append(dev)

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
            delay = 0.1/self.app.scale_factor
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
        else:
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
                ])

        if not silent:
            self.view.show_apply_spinner()
        ts = TaskSequence(self.run_in_bg, tasks, ApplyWatcher(self.view, self))
        ts.run()
        if dhcp_device_versions:
            self.dhcp_check_handle = self.loop.set_alarm_in(
                10,
                lambda loop, ud: self.check_dchp_results(ud),
                dhcp_device_versions)

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
