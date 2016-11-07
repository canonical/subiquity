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

import copy
from functools import partial
import glob
import logging
import os
import queue
import random
import select
import socket
import subprocess

import yaml

from probert.network import UdevObserver

from subiquitycore.async import Async
from subiquitycore.models import NetworkModel
from subiquitycore.ui.views import (NetworkView,
                                    NetworkSetDefaultRouteView,
                                    NetworkBondInterfacesView,
                                    NetworkConfigureInterfaceView,
                                    NetworkConfigureIPv4InterfaceView,
                                    NetworkConfigureWLANView)
from subiquitycore.ui.views.network import ApplyingConfigWidget
from subiquitycore.ui.dummy import DummyView
from subiquitycore.controller import BaseController
from subiquitycore.utils import run_command_start, run_command_summarize

log = logging.getLogger("subiquitycore.controller.network")


class BackgroundTask:
    """Something that runs without blocking the UI and can be canceled."""

    def run(self):
        raise NotImplementedError(self.run)

    def cancel(self):
        raise NotImplementedError(self.cancel)


class BackgroundProcess(BackgroundTask):

    def __init__(self, cmd):
        self.cmd = cmd
        self.proc = None

    def __repr__(self):
        return 'BackgroundProcess(%r)'%(self.cmd,)

    def run(self, observer):
        self.proc = run_command_start(self.cmd)
        stdout, stderr = self.proc.communicate()
        result = run_command_summarize(self.proc, stdout, stderr)
        if result['status'] == 0:
            observer.task_succeeded()
        else:
            observer.task_failed(result['err'])

    def cancel(self):
        if self.proc is None:
            return
        try:
            self.proc.terminate()
        except ProcessLookupError:
            pass # It's OK if the process has already terminated.


class PythonSleep(BackgroundTask):

    def __init__(self, duration):
        self.duration = duration
        self.r, self.w = os.pipe()

    def __repr__(self):
        return 'PythonSleep(%r)'%(self.duration,)

    def run(self, observer):
        r, _, _ = select.select([self.r], [], [], self.duration)
        if not r:
            observer.task_succeeded()
        os.close(self.r)
        os.close(self.w)

    def cancel(self):
        os.write(self.w, b'x')


class WaitForDefaultRouteTask(BackgroundTask):

    def __init__(self, timeout, udev_observer):
        self.timeout = timeout
        self.fail_r, self.fail_w = os.pipe()
        self.success_r, self.success_w = os.pipe()
        self.udev_observer = udev_observer

    def __repr__(self):
        return 'WaitForDefaultRouteTask(%r)'%(self.timeout,)

    def got_route(self):
        os.write(self.success_w, b'x')

    def run(self, observer):
        self.udev_observer.add_default_route_waiter(self.got_route)
        try:
            r, _, _ = select.select([self.fail_r, self.success_r], [], [], self.timeout)
            if self.success_r in r:
                observer.task_succeeded()
            else:
                observer.task_failed()
        finally:
            os.close(self.fail_r)
            os.close(self.fail_w)
            os.close(self.success_r)
            os.close(self.success_w)

    def cancel(self):
        os.write(self.fail_w, b'x')


class TaskSequence:
    def __init__(self, loop, tasks, watcher):
        self.loop = loop
        self.tasks = tasks
        self.watcher = watcher
        self.canceled = False
        self.stage = None
        self.curtask = None
        self.incoming = queue.Queue()
        self.outgoing = queue.Queue()
        self.pipe = self.loop.watch_pipe(self._thread_callback)

    def run(self):
        self._run1()

    def cancel(self):
        if self.curtask is not None:
            log.debug("canceling %s", self.curtask)
            self.curtask.cancel()
        self.canceled = True

    def _run1(self):
        self.stage, self.curtask = self.tasks[0]
        self.tasks = self.tasks[1:]
        log.debug('running %s for stage %s', self.curtask, self.stage)
        def cb(fut):
            # We do this just so that any exceptions raised don't get lost.
            # Vomiting a traceback all over the console is nasty, but not as
            # nasty as silently doing nothing.
            fut.result()
        Async.pool.submit(self.curtask.run, self).add_done_callback(cb)

    def call_from_thread(self, func, *args):
        log.debug('call_from_thread %s %s', func, args)
        self.incoming.put((func, args))
        os.write(self.pipe, b'x')
        self.outgoing.get()

    def _thread_callback(self, ignored):
        func, args = self.incoming.get()
        func(*args)
        self.outgoing.put(None)

    def task_succeeded(self):
        self.call_from_thread(self._task_succeeded)

    def _task_succeeded(self):
        if self.canceled:
            return
        self.watcher.task_complete(self.stage)
        if len(self.tasks) == 0:
            self.watcher.tasks_finished()
        else:
            self._run1()

    def task_failed(self, info=None):
        if self.canceled:
            return
        self.call_from_thread(self.watcher.task_error, self.stage, info)


def view(func):
    n = func.__name__
    def f(self, *args, **kw):
        m = getattr(self, n)
        self.view_stack.append((m, args, kw))
        return func(self, *args, **kw)
    return f

netplan_config_file_name = '00-snapd-config.yaml'

def sanitize_config(config):
    """Return a copy of config with passwords redacted."""
    config = copy.deepcopy(config)
    for iface, iface_config in config.get('network', {}).get('wifis', {}).items():
        for ap, ap_config in iface_config.get('access-points', {}).items():
            if 'password' in ap_config:
                ap_config['password'] = '<REDACTED>'
    return config

class SubiquityObserver(UdevObserver):
    def __init__(self, model, ui, loop):
        UdevObserver.__init__(self)
        self.model = model
        self.ui = ui
        self.loop = loop
        self.default_route_waiter = None
        self.default_routes = set()

    def start(self):
        fds = super().start()
        for fd in fds:
            self.loop.watch_file(fd, partial(self.data_ready, fd))
        return fds

    def new_link(self, ifindex, link):
        self.model.new_link(ifindex, link)

    def del_link(self, ifindex):
        self.model.del_link(ifindex)
        if ifindex in self.default_routes:
            self.default_routes.remove(ifindex)

    def update_link(self, ifindex):
        self.model.update_link(ifindex)

    def route_change(self, action, data):
        if data['dst'] != b'default':
            return
        if data['table'] != 254:
            return
        super().route_change(action, data)
        ifindex = data['ifindex']
        if action == "NEW":
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

    def refresh(self):
        v = self.ui.frame.body
        if hasattr(v, 'refresh_model_inputs'):
            v.refresh_model_inputs()
        if self.default_route_waiter:
            pass

    def data_ready(self, fd):
        code = subprocess.call(['udevadm', 'settle', '-t', '0'])
        if code != 0:
            log.debug("waiting 0.1 to let udev event queue settle")
            self.loop.set_alarm_in(0.1, lambda loop, ud:self.data_ready(fd))
        super().data_ready(fd)
        self.refresh()


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
'''

class NetworkController(BaseController):
    signals = [
        ('menu:network:main:set-default-v4-route',     'set_default_v4_route'),
        ('menu:network:main:set-default-v6-route',     'set_default_v6_route'),
    ]

    root = "/"

    def __init__(self, common):
        super().__init__(common)
        self.model = NetworkModel()
        if self.opts.dry_run:
            import atexit, shutil, tempfile
            self.root = tempfile.mkdtemp()
            self.tried_once = False
            atexit.register(shutil.rmtree, self.root)
            os.makedirs(os.path.join(self.root, 'etc/netplan'))
            with open(os.path.join(self.root, 'etc/netplan', netplan_config_file_name), 'w') as fp:
                fp.write(default_netplan)

        configs_by_basename = {}
        paths = glob.glob(os.path.join(self.root, 'lib/netplan', "*.yaml")) + \
          glob.glob(os.path.join(self.root, 'etc/netplan', "*.yaml")) + \
          glob.glob(os.path.join(self.root, 'run/netplan', "*.yaml"))
        for path in paths:
            configs_by_basename[os.path.basename(path)] = path
        for _, path in sorted(configs_by_basename.items()):
            try:
                fp = open(path)
            except OSError:
                log.exception("opening %s failed", path)
            with fp:
                self.model.parse_netplan_config(fp.read())

        self.view_stack = []

        self.observer = SubiquityObserver(self.model, self.ui, self.loop)
        self.observer.start()

        self.view_stack = []

    def prev_view(self):
        self.view_stack.pop()
        meth, args, kw = self.view_stack.pop()
        meth(*args, **kw)

    def start_scan(self, dev):
        self.observer.wlan_listener.trigger_scan(dev.ifindex)

    def cancel(self):
        if len(self.view_stack) <= 1:
            self.signal.emit_signal('prev-screen')
        else:
            self.prev_view()

    def default(self):
        self.view_stack = []
        self.start()

    @view
    def start(self):
        title = "Network connections"
        excerpt = ("Configure at least the main interface this server will "
                   "use to receive updates.")
        footer = ("Additional networking info here")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 20)
        self.ui.set_body(NetworkView(self.model, self))

    def network_finish(self, config):
        log.debug("network config: \n%s", yaml.dump(sanitize_config(config), default_flow_style=False))

        netplan_path = os.path.join(self.root, 'etc/netplan', netplan_config_file_name)
        while True:
            try:
                tmppath = '%s.%s' % (netplan_path, random.randrange(0, 1000))
                fd = os.open(tmppath, os.O_WRONLY | os.O_EXCL | os.O_CREAT, 0o0600)
            except FileExistsError:
                continue
            else:
                break
        w = os.fdopen(fd, 'w')
        with w:
            w.write("# This is the network config written by 'console-conf'\n")
            w.write(yaml.dump(config))
        os.rename(tmppath, netplan_path)
        if self.opts.dry_run:
            tasks = [
                ('one', BackgroundProcess(['sleep', '0.1'])),
                ('two', PythonSleep(0.1)),
                ('three', BackgroundProcess(['sleep', '0.1'])),
                ]
            if os.path.exists('/lib/netplan/generate'):
                # If netplan appears to be installed, run generate to at
                # least test that what we wrote is acceptable to netplan.
                tasks.append(('generate', BackgroundProcess(['netplan', 'generate', '--root', self.root])))
            if not self.tried_once:
                tasks.append(('fail', WaitForDefaultRouteTask(30, self.observer)))
                tasks.append(('fail', BackgroundProcess(['false'])))
                self.tried_once = True
        else:
            tasks = [
                ('generate', BackgroundProcess(['/lib/netplan/generate'])),
                ('apply', BackgroundProcess(['netplan', 'apply'])),
                ('timeout', WaitForDefaultRouteTask(30, self.observer)),
                ]

        def cancel():
            self.cs.cancel()
            self.task_error('canceled')
        self.acw = ApplyingConfigWidget(len(tasks), cancel)
        self.ui.frame.body.show_overlay(self.acw)

        self.cs = TaskSequence(self.loop, tasks, self)
        self.cs.run()

    def task_complete(self, stage):
        self.acw.advance()

    def task_error(self, stage, info=None):
        self.ui.frame.body.remove_overlay(self.acw)
        self.ui.frame.body.show_network_error(stage, info)

    def tasks_finished(self):
        self.signal.emit_signal('next-screen')


    @view
    def set_default_v4_route(self):
        self.ui.set_header("Default route")
        self.ui.set_body(NetworkSetDefaultRouteView(self.model, socket.AF_INET, self))

    @view
    def set_default_v6_route(self):
        self.ui.set_header("Default route")
        self.ui.set_body(NetworkSetDefaultRouteView(self.model, socket.AF_INET6, self))

    @view
    def bond_interfaces(self):
        self.ui.set_header("Bond interfaces")
        self.ui.set_body(NetworkBondInterfacesView(self.model, self))

    @view
    def network_configure_interface(self, iface):
        self.ui.set_header("Network interface {}".format(iface))
        self.ui.set_body(NetworkConfigureInterfaceView(self.model, self, iface))

    @view
    def network_configure_ipv4_interface(self, iface):
        self.ui.set_header("Network interface {} manual IPv4 "
                           "configuration".format(iface))
        self.ui.set_body(NetworkConfigureIPv4InterfaceView(self.model, self, iface))

    @view
    def network_configure_wlan_interface(self, iface):
        self.ui.set_header("Network interface {} manual IPv4 "
                           "configuration".format(iface))
        self.ui.set_body(NetworkConfigureWLANView(self.model, self, iface))

    @view
    def network_configure_ipv6_interface(self, iface):
        self.ui.set_body(DummyView(self))

    @view
    def install_network_driver(self):
        self.ui.set_body(DummyView(self))

