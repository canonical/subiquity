# Copyright 2015 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import abc
import asyncio
import contextlib
import logging
import os
import pathlib
import subprocess
from typing import Optional

import pyroute2
import yaml
from probert.network import IFF_UP, NetworkEventReceiver

from subiquitycore import netplan
from subiquitycore.async_helpers import SingleInstanceTask
from subiquitycore.context import with_context
from subiquitycore.controller import BaseController
from subiquitycore.file_util import write_file
from subiquitycore.models.network import (
    BondConfig,
    DHCPState,
    NetDevAction,
    StaticConfig,
    WLANConfig,
)
from subiquitycore.pubsub import CoreChannels
from subiquitycore.tuicontroller import TuiController
from subiquitycore.ui.stretchy import StretchyOverlay
from subiquitycore.ui.views.network import NetworkView
from subiquitycore.utils import arun_command, orig_environ, run_command

log = logging.getLogger("subiquitycore.controllers.network")


class SubiquityNetworkEventReceiver(NetworkEventReceiver):
    def __init__(self, controller):
        self.controller = controller
        self.model = controller.model
        self.has_default_route = False

    def new_link(self, ifindex, link):
        netdev = self.model.new_link(ifindex, link)
        if netdev is not None:
            self.controller.new_link(netdev)

    def del_link(self, ifindex):
        netdev = self.model.del_link(ifindex)
        self.probe_default_routes()
        self.controller.update_has_default_route(self.has_default_route)
        if netdev is not None:
            self.controller.del_link(netdev)

    def update_link(self, ifindex):
        netdev = self.model.update_link(ifindex)
        if netdev is None:
            return
        flags = getattr(netdev.info, "flags", 0)
        if not (flags & IFF_UP):
            self.probe_default_routes()
            self.controller.update_has_default_route(self.has_default_route)
        self.controller.update_link(netdev)

    def route_change(self, action, data):
        super().route_change(action, data)
        if data["dst"] != "default":
            return
        if data["table"] != 254:
            return
        self.probe_default_routes()
        self.controller.update_has_default_route(self.has_default_route)

    def _default_route_exists(self, routes):
        return any(route["table"] == 254 and not route["dst"] for route in routes)

    def probe_default_routes(self):
        with pyroute2.NDB() as ndb:
            self.has_default_route = self._default_route_exists(ndb.routes)
        log.debug("default routes %s", self.has_default_route)

    @staticmethod
    def create(
        controller: BaseController, dry_run: bool
    ) -> "SubiquityNetworkEventReceiver":
        if dry_run:
            return DryRunSubiquityNetworkEventReceiver(controller)
        else:
            return SubiquityNetworkEventReceiver(controller)


class DryRunSubiquityNetworkEventReceiver(SubiquityNetworkEventReceiver):
    def probe_default_routes(self):
        self.has_default_route = True
        log.debug("dryrun default routes %s", self.has_default_route)


default_netplan = """
network:
  version: 2
  ethernets:
    "all-en":
       match:
         name: "en*"
       addresses:
         - 10.0.2.15/24
       nameservers:
         addresses:
           - 8.8.8.8
           - 8.4.8.4
         search:
           - foo
           - bar
       routes:
         - to: default
           via: 10.0.2.2
    "all-eth":
       match:
         name: "eth*"
       dhcp4: true
  wifis:
    "wlsp4":
       dhcp4: true
       access-points:
         "some-ap":
            password: password
"""


class BaseNetworkController(BaseController):
    model_name = "network"
    root = "/"

    def __init__(self, app):
        super().__init__(app)
        self.apply_config_task = SingleInstanceTask(self._apply_config)
        if self.opts.dry_run:
            self.root = os.path.abspath(self.opts.output_base)
            netplan_path = self.netplan_path
            netplan_dir = os.path.dirname(netplan_path)
            if os.path.exists(netplan_dir):
                import shutil

                shutil.rmtree(netplan_dir)
            os.makedirs(netplan_dir)
            with open(netplan_path, "w") as fp:
                fp.write(default_netplan)
        self.parse_netplan_configs()

        self._watching = False
        self.network_event_receiver = SubiquityNetworkEventReceiver.create(
            self, self.opts.dry_run
        )

    def parse_netplan_configs(self):
        self.model.parse_netplan_configs(self.root)

    def start(self):
        self._observer_handles = []
        self.observer, self._observer_fds = self.app.prober.probe_network(
            self.network_event_receiver
        )
        self.start_watching()

    def stop_watching(self):
        if not self._watching:
            return
        loop = asyncio.get_running_loop()
        for fd in self._observer_fds:
            loop.remove_reader(fd)
        self._watching = False

    def start_watching(self):
        if self._watching:
            return
        loop = asyncio.get_running_loop()
        for fd in self._observer_fds:
            loop.add_reader(fd, self._data_ready, fd)
        self._watching = True

    def _data_ready(self, fd):
        cp = run_command(["udevadm", "settle", "-t", "0"])
        if cp.returncode != 0:
            log.debug("waiting 0.1 to let udev event queue settle")
            self.stop_watching()
            loop = asyncio.get_running_loop()
            loop.call_later(0.1, self.start_watching)
            return
        self.observer.data_ready(fd)

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

    @property
    def netplan_path(self):
        if self.opts.project == "subiquity":
            netplan_config_file_name = "00-installer-config.yaml"
        else:
            netplan_config_file_name = "00-snapd-config.yaml"
        return os.path.join(self.root, "etc/netplan", netplan_config_file_name)

    def apply_config(self, context=None, silent=False):
        self.apply_config_task.start_sync(context=context, silent=silent)

    async def _down_devs(self, devs):
        for dev in devs:
            try:
                log.debug("downing %s", dev.name)
                self.observer.rtlistener.unset_link_flags(dev.ifindex, IFF_UP)
            except RuntimeError:
                # We don't actually care very much about this
                log.exception("unset_link_flags failed for %s", dev.name)

    async def _delete_devs(self, devs):
        for dev in devs:
            # XXX would be nicer to do this via rtlistener eventually.
            log.debug("deleting %s", dev.name)
            cmd = ["ip", "link", "delete", "dev", dev.name]
            try:
                await arun_command(cmd, check=True)
            except subprocess.CalledProcessError as cp:
                log.info("deleting %s failed with %r", dev.name, cp.stderr)

    def _write_config(self):
        config = self.model.render_config()

        log.debug(
            "network config: \n%s",
            yaml.dump(netplan.sanitize_config(config), default_flow_style=False),
        )

        for p in netplan.configs_in_root(self.root, masked=True):
            if p == self.netplan_path:
                continue
            os.rename(p, p + ".dist-" + self.opts.project)

        write_file(self.netplan_path, self.model.stringify_config(config))

        self.parse_netplan_configs()

    @with_context(name="apply_config", description="silent={silent}", level="INFO")
    async def _apply_config(self, *, context, silent):
        devs_to_delete = []
        devs_to_down = []
        dhcp_device_versions = []
        dhcp_events = set()
        for dev in self.model.get_all_netdevs(include_deleted=True):
            dev.dhcp_events = {}
            for v in 4, 6:
                if dev.dhcp_enabled(v):
                    if not silent:
                        dev.set_dhcp_state(v, DHCPState.PENDING)
                        self.network_event_receiver.update_link(dev.ifindex)
                    else:
                        dev.set_dhcp_state(v, DHCPState.RECONFIGURE)
                    dev.dhcp_events[v] = e = asyncio.Event()
                    dhcp_events.add(e)
            if dev.info is None:
                continue
            if dev.config != self.model.config.config_for_device(dev.info):
                if dev.is_virtual:
                    devs_to_delete.append(dev)
                else:
                    devs_to_down.append(dev)

        self._write_config()

        if not silent:
            self.apply_starting()

        try:

            def error(stage):
                if not silent:
                    self.apply_error(stage)

            if self.opts.dry_run:
                delay = 1 / self.app.scale_factor
                await arun_command(["sleep", str(delay)])

                # /usr/libexec/netplan/generate exists starting with 22.04.
                # When we stop supporting 20.04, we should drop the
                # reference to /lib/netplan/generate.
                netplan_generator_legacy = pathlib.Path("/lib/netplan/generate")
                netplan_generator = pathlib.Path("/usr/libexec/netplan/generate")

                if netplan_generator.exists() or netplan_generator_legacy.exists():
                    # If netplan appears to be installed, run generate to
                    # at least test that what we wrote is acceptable to
                    # netplan but clear the SNAP environment variable to
                    # avoid that netplan thinks its running in a snap and
                    # tries to call netplan over the system bus.
                    env = os.environ.copy()
                    with contextlib.suppress(KeyError):
                        del env["SNAP"]
                    await arun_command(
                        ["netplan", "generate", "--root", self.root],
                        check=True,
                        env=env,
                    )
            else:
                if devs_to_down or devs_to_delete:
                    try:
                        await arun_command(
                            [
                                "systemctl",
                                "mask",
                                "--runtime",
                                "systemd-networkd.service",
                                "systemd-networkd.socket",
                            ],
                            check=True,
                        )
                        await arun_command(
                            [
                                "systemctl",
                                "stop",
                                "systemd-networkd.service",
                                "systemd-networkd.socket",
                            ],
                            check=True,
                        )
                    except subprocess.CalledProcessError:
                        error("stop-networkd")
                        raise
                if devs_to_down:
                    await self._down_devs(devs_to_down)
                if devs_to_delete:
                    await self._delete_devs(devs_to_delete)
                if devs_to_down or devs_to_delete:
                    await arun_command(
                        [
                            "systemctl",
                            "unmask",
                            "--runtime",
                            "systemd-networkd.service",
                            "systemd-networkd.socket",
                        ],
                        check=True,
                    )
                env = orig_environ(None)
                try:
                    await arun_command(["netplan", "apply"], env=env, check=True)
                except subprocess.CalledProcessError as cpe:
                    log.debug(
                        f"CalledProcessError: stdout[{cpe.stdout}] stderr[{cpe.stderr}]"
                    )
                    error("apply")
                    raise
                if devs_to_down or devs_to_delete:
                    # It's probably running already, but just in case.
                    await arun_command(
                        ["systemctl", "start", "systemd-networkd.socket"], check=False
                    )
        finally:
            if not silent:
                self.apply_stopping()

        if not dhcp_events:
            return

        try:
            await asyncio.wait_for(
                asyncio.wait({asyncio.create_task(e.wait()) for e in dhcp_events}), 10
            )
        except asyncio.TimeoutError:
            pass

        for dev, v in dhcp_device_versions:
            dev.dhcp_events = {}
            if not dev.dhcp_addresses()[v]:
                dev.set_dhcp_state(v, DHCPState.TIMED_OUT)
                self.network_event_receiver.update_link(dev.ifindex)

    def set_static_config(
        self, dev_name: str, ip_version: int, static_config: StaticConfig
    ) -> None:
        dev = self.model.get_netdev_by_name(dev_name)
        dev.remove_ip_networks_for_version(ip_version)
        dev.config.setdefault("addresses", []).extend(static_config.addresses)
        if static_config.gateway:
            dev.config["routes"] = [{"to": "default", "via": static_config.gateway}]
        else:
            dev.remove_routes(ip_version)
        ns = dev.config.setdefault("nameservers", {})
        ns.setdefault("addresses", []).extend(static_config.nameservers)
        ns.setdefault("search", []).extend(static_config.searchdomains)
        self.update_link(dev)
        self.apply_config()

    def enable_dhcp(self, dev_name: str, ip_version: int) -> None:
        dev = self.model.get_netdev_by_name(dev_name)
        dev.remove_ip_networks_for_version(ip_version)
        dhcpkey = "dhcp{v}".format(v=ip_version)
        dev.config[dhcpkey] = True
        self.update_link(dev)
        self.apply_config()

    def disable_network(self, dev_name: str, ip_version: int) -> None:
        dev = self.model.get_netdev_by_name(dev_name)
        dev.remove_ip_networks_for_version(ip_version)
        self.update_link(dev)
        self.apply_config()

    def add_vlan(self, dev_name: str, id: int):
        new = self.model.new_vlan(dev_name, id)
        self.new_link(new)
        dev = self.model.get_netdev_by_name(dev_name)
        self.update_link(dev)
        self.apply_config()

    def delete_link(self, dev_name: str):
        dev = self.model.get_netdev_by_name(dev_name)
        touched_devices = set()
        if dev.type == "bond":
            for device_name in dev.config["interfaces"]:
                interface = self.model.get_netdev_by_name(device_name)
                touched_devices.add(interface)
        elif dev.type == "vlan":
            link = self.model.get_netdev_by_name(dev.config["link"])
            touched_devices.add(link)
        dev.config = None
        self.del_link(dev)
        for dev in touched_devices:
            self.update_link(dev)
        self.apply_config()

    def add_or_update_bond(
        self, existing_name: Optional[str], new_name: str, new_info: BondConfig
    ) -> None:
        get_netdev_by_name = self.model.get_netdev_by_name
        touched_devices = set()
        for device_name in new_info.interfaces:
            device = get_netdev_by_name(device_name)
            device.config = {}
            touched_devices.add(device)
        if existing_name is None:
            new_dev = self.model.new_bond(new_name, new_info)
            self.new_link(new_dev)
        else:
            existing = get_netdev_by_name(existing_name)
            for interface in existing.config["interfaces"]:
                touched_devices.add(get_netdev_by_name(interface))
            existing.config.update(new_info.to_config())
            if existing.name != new_name:
                config = existing.config
                existing.config = None
                self.del_link(existing)
                existing.config = config
                existing.name = new_name
                self.new_link(existing)
            else:
                touched_devices.add(existing)
        for dev in touched_devices:
            self.update_link(dev)
        self.apply_config()

    async def get_info_for_netdev(self, dev_name: str) -> str:
        device = self.model.get_netdev_by_name(dev_name)
        if device.info is not None:
            return yaml.dump(device.info.serialize(), default_flow_style=False)
        else:
            return "Configured but not yet created {type} interface.".format(
                type=device.type
            )

    def set_wlan(self, dev_name: str, wlan: WLANConfig) -> None:
        device = self.model.get_netdev_by_name(dev_name)
        cur_ssid, cur_psk = device.configured_ssid
        if wlan.ssid and not cur_ssid:
            # Turn DHCP4 on by default when specifying an SSID for
            # the first time...
            device.config["dhcp4"] = True
        device.set_ssid_psk(wlan.ssid, wlan.psk)
        self.update_link(device)
        self.apply_config()

    def start_scan(self, dev_name: str) -> None:
        device = self.model.get_netdev_by_name(dev_name)
        try:
            self.observer.trigger_scan(device.ifindex)
        except RuntimeError as r:
            device.info.wlan["scan_state"] = "error %s" % (r,)
        self.update_link(device)

    @abc.abstractmethod
    def apply_starting(self):
        pass

    @abc.abstractmethod
    def apply_stopping(self):
        pass

    @abc.abstractmethod
    def apply_error(self, stage):
        pass

    @abc.abstractmethod
    def update_has_default_route(self, has_default_route):
        if has_default_route:
            self.app.hub.broadcast(CoreChannels.NETWORK_UP)

    @abc.abstractmethod
    def new_link(self, netdev):
        pass

    @abc.abstractmethod
    def update_link(self, netdev):
        for v, e in netdev.dhcp_events.items():
            if netdev.dhcp_addresses()[v]:
                netdev.set_dhcp_state(v, DHCPState.CONFIGURED)
                e.set()
        pass

    @abc.abstractmethod
    def del_link(self, netdev):
        pass


class NetworkAnswersMixin:
    async def run_answers(self):
        if self.answers.get("accept-default", False):
            self.done()
        elif self.answers.get("actions", False):
            actions = self.answers["actions"]
            self.answers.clear()
            await self._run_actions(actions)

    def _action_get(self, id):
        dev_spec = id[0].split()
        if dev_spec[0] == "interface":
            if dev_spec[1] == "index":
                name = self.view.cur_netdev_names[int(dev_spec[2])]
            elif dev_spec[1] == "name":
                name = dev_spec[2]
            return self.view.dev_name_to_table[name]
        raise Exception("could not resolve {}".format(id))

    def _action_clean_interfaces(self, devices):
        r = [self._action_get(device).dev_info.name for device in devices]
        log.debug("%s", r)
        return r

    async def _answers_action(self, action):
        log.debug("_answers_action %r", action)
        if "obj" in action:
            table = self._action_get(action["obj"])
            meth = getattr(self.ui.body, "_action_{}".format(action["action"]))
            action_obj = getattr(NetDevAction, action["action"])
            self.ui.body._action(table, None, (action_obj, meth))
            yield
            body = self.ui.body._w
            if action["action"] == "DELETE":
                t = 0.0
                while table.dev_info.name in self.view.cur_netdev_names:
                    await asyncio.sleep(0.1)
                    t += 0.1
                    if t > 5.0:
                        raise Exception("interface did not disappear in 5 secs")
                log.debug("waited %s for interface to disappear", t)
            if not isinstance(body, StretchyOverlay):
                return
            for k, v in action.items():
                if not k.endswith("data"):
                    continue
                form_name = "form"
                submit_key = "submit"
                if "-" in k:
                    prefix = k.split("-")[0]
                    form_name = prefix + "_form"
                    submit_key = prefix + "-submit"
                async for _ in self._enter_form_data(
                    getattr(body.stretchy, form_name), v, action.get(submit_key, True)
                ):
                    pass
        elif action["action"] == "create-bond":
            self.ui.body._create_bond()
            yield
            body = self.ui.body._w
            data = action["data"].copy()
            if "devices" in data:
                data["interfaces"] = data.pop("devices")
                async for _ in self._enter_form_data(
                    body.stretchy.form, data, action.get("submit", True)
                ):
                    pass
            t = 0.0
            while data["name"] not in self.view.cur_netdev_names:
                await asyncio.sleep(0.1)
                t += 0.1
                if t > 5.0:
                    raise Exception("bond did not appear in 5 secs")
            if t > 0:
                log.debug("waited %s for bond to appear", t)
            yield
        elif action["action"] == "done":
            self.ui.body.done()
        else:
            raise Exception("could not process action {}".format(action))


class NetworkController(BaseNetworkController, TuiController, NetworkAnswersMixin):
    def __init__(self, app):
        super().__init__(app)
        self.view = None
        self.view_shown = False

    def make_ui(self):
        if not self.view_shown:
            self.update_initial_configs()
        netdev_infos = [dev.netdev_info() for dev in self.model.get_all_netdevs()]
        self.view = NetworkView(self, netdev_infos)
        if not self.view_shown:
            self.apply_config(silent=True)
            self.view_shown = True
        self.view.update_has_default_route(
            self.network_event_receiver.has_default_route
        )
        return self.view

    def end_ui(self):
        self.view = None

    def done(self):
        log.debug("NetworkController.done next_screen")
        self.model.has_network = self.network_event_receiver.has_default_route
        self.app.request_next_screen()

    def cancel(self):
        self.app.request_prev_screen()

    def apply_starting(self):
        super().apply_starting()
        if self.view is not None:
            self.view.show_apply_spinner()

    def apply_stopping(self):
        super().apply_stopping()
        if self.view is not None:
            self.view.hide_apply_spinner()

    def apply_error(self, stage):
        super().apply_error(stage)
        if self.view is not None:
            self.view.show_network_error(stage)

    def update_has_default_route(self, has_default_route):
        super().update_has_default_route(has_default_route)
        if self.view:
            self.view.update_has_default_route(has_default_route)

    def new_link(self, netdev):
        super().new_link(netdev)
        if self.view is not None:
            self.view.new_link(netdev.netdev_info())

    def update_link(self, netdev):
        super().update_link(netdev)
        if self.view is not None:
            self.view.update_link(netdev.netdev_info())

    def del_link(self, netdev):
        super().del_link(netdev)
        if self.view is not None:
            self.view.del_link(netdev.netdev_info())
