# Copyright 2019 Canonical, Ltd.
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

import asyncio
import logging
from typing import List, Optional

import aiohttp

from subiquity.common.api.client import make_client_for_conn
from subiquity.common.apidef import API, LinkAction, NetEventAPI
from subiquity.common.errorreport import ErrorReportKind
from subiquity.common.types import NetworkStatus, PackageInstallState
from subiquity.server.controller import SubiquityController
from subiquitycore.async_helpers import run_bg_task, schedule_task
from subiquitycore.context import with_context
from subiquitycore.controllers.network import BaseNetworkController
from subiquitycore.models.network import BondConfig, StaticConfig, WLANConfig

log = logging.getLogger("subiquity.server.controllers.network")

MATCH = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "macaddress": {"type": "string"},
        "driver": {"type": "string"},
    },
    "additionalProperties": False,
}

NETPLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "version": {
            "type": "integer",
            "minimum": 2,
            "maximum": 2,
        },
        "ethernets": {
            "type": "object",
            "properties": {
                "match": MATCH,
            },
        },
        "wifis": {
            "type": "object",
            "properties": {
                "match": MATCH,
            },
        },
        "bridges": {"type": "object"},
        "bonds": {"type": "object"},
        "tunnels": {"type": "object"},
        "vlans": {"type": "object"},
    },
    "required": ["version"],
}


class NetworkController(BaseNetworkController, SubiquityController):
    endpoint = API.network

    ai_data = None
    autoinstall_key = "network"
    autoinstall_schema = {
        "oneOf": [
            NETPLAN_SCHEMA,
            {
                "type": "object",
                "properties": {
                    "network": NETPLAN_SCHEMA,
                },
                "required": ["network"],
            },
        ],
    }

    def __init__(self, app):
        super().__init__(app)
        app.note_file_for_apport("NetplanConfig", self.netplan_path)
        self.view_shown = False
        self.clients = {}
        self.install_wpasupplicant_task = None
        self.pending_wlan_devices = set()
        self.with_wlan_listener = app.opts.with_wlan_listener

    def maybe_start_install_wpasupplicant(self):
        log.debug("maybe_start_install_wpasupplicant")
        if self.install_wpasupplicant_task is not None:
            return
        self.install_wpasupplicant_task = asyncio.create_task(
            self._install_wpasupplicant()
        )

    def wlan_support_install_state(self):
        return self.app.package_installer.state_for_pkg("wpasupplicant")

    async def _install_wpasupplicant(self):
        r = await self.app.package_installer.install_pkg("wpasupplicant")
        log.debug("wlan_support_install_finished %s", r)
        self._call_clients("wlan_support_install_finished", r)
        if r == PackageInstallState.DONE:
            for dev in self.pending_wlan_devices:
                self._send_update(LinkAction.NEW, dev)
        self.pending_wlan_devices = set()
        return r

    def load_autoinstall_data(self, data):
        if data is not None:
            self.ai_data = data
            # The version included with 20.04 accidentally required
            # that you put:
            #
            # network:
            #   network:
            #     version: 2
            #
            # in your autoinstall config. Continue to support that for
            # backwards compatibility.
            if "network" in self.ai_data:
                self.ai_data = self.ai_data["network"]

    def start(self):
        if self.ai_data is not None:
            self.model.override_config = {"network": self.ai_data}
            self.apply_config()
            if self.interactive():
                # If interactive, we want edits in the UI to override
                # the provided config. If not, we just splat the
                # autoinstall config onto the target system.
                schedule_task(self.unset_override_config())
        elif not self.interactive():
            self.initial_config = schedule_task(self.wait_for_initial_config())
        super().start()

    async def unset_override_config(self):
        await self.apply_config_task.wait()
        self.model.override_config = None

    @with_context()
    async def wait_for_initial_config(self, context):
        # In interactive mode, we disable all nics that haven't got an
        # address by the time we get to the network screen. But in
        # non-interactive mode we might get to that screen much faster
        # so we wait for up to 10 seconds for any device configured
        # to use dhcp to get an address.
        dhcp_events = set()
        for dev in self.model.get_all_netdevs(include_deleted=True):
            dev.dhcp_events = {}
            for v in 4, 6:
                if dev.dhcp_enabled(v) and not dev.dhcp_addresses()[v]:
                    dev.dhcp_events[v] = e = asyncio.Event()
                    dhcp_events.add(e)
        if not dhcp_events:
            return

        with context.child("wait_dhcp"):
            try:
                await asyncio.wait_for(
                    asyncio.wait({asyncio.create_task(e.wait()) for e in dhcp_events}),
                    10,
                )
            except asyncio.TimeoutError:
                pass

    @with_context()
    async def apply_autoinstall_config(self, context):
        want_apply_config = True
        if self.ai_data is None:
            if not await self.model.is_nm_enabled():
                with context.child("wait_initial_config"):
                    await self.initial_config
                self.update_initial_configs()
                self.apply_config(context)
            else:
                log.debug(
                    "NetworkManager is enabled and no network"
                    " autoinstall section was found. Not applying"
                    " network settings."
                )
                want_apply_config = False
        if want_apply_config:
            with context.child("wait_for_apply"):
                await self.apply_config_task.wait()
        else:
            # Make sure we have read at least once the routing table.
            # Careful, the following is a blocking call. But running it in a
            # separate thread without locking sounds unsafe too.
            self.network_event_receiver.probe_default_routes()
        self.model.has_network = self.network_event_receiver.has_default_route

    async def _apply_config(self, *, context=None, silent=False):
        try:
            await super()._apply_config(context=context, silent=silent)
        except asyncio.CancelledError:
            # asyncio.CancelledError is a subclass of Exception in
            # Python 3.6 (sadface)
            raise
        except Exception:
            log.exception("_apply_config failed")
            self.model.has_network = False
            self.app.make_apport_report(
                ErrorReportKind.NETWORK_FAIL, "applying network"
            )
            if not self.interactive():
                raise

    def make_autoinstall(self):
        return self.model.render_config()["network"]

    async def GET(self) -> NetworkStatus:
        if not self.view_shown:
            self.update_initial_configs()
            self.apply_config(silent=True)
            self.view_shown = True
        if self.wlan_support_install_state() == PackageInstallState.DONE:
            devices = self.model.get_all_netdevs()
        else:
            devices = [
                dev for dev in self.model.get_all_netdevs() if dev.type != "wlan"
            ]
        return NetworkStatus(
            devices=[dev.netdev_info() for dev in devices],
            wlan_support_install_state=self.wlan_support_install_state(),
        )

    async def configured(self):
        # There may be some instances in which the network controller
        # is interactive but is only ever marked configured (through a
        # POST to either /network or /meta/mark_configured) and is never
        # interacted with otherwise (via GET) such that we don't disable
        # interfaces which don't have a global IP.
        if self.interactive() and not self.view_shown:
            self.update_initial_configs()

        self.model.has_network = self.network_event_receiver.has_default_route
        self.model.needs_wpasupplicant = (
            self.wlan_support_install_state() == PackageInstallState.DONE
        )
        await super().configured()

    async def POST(self) -> None:
        await self.configured()

    async def global_addresses_GET(self) -> List[str]:
        ips: List[str] = []
        for dev in self.model.get_all_netdevs():
            if dev.info is None:
                continue
            ips.extend(map(str, dev.actual_global_ip_addresses))
        return ips

    async def subscription_PUT(self, socket_path: str) -> None:
        log.debug("added subscription %s", socket_path)
        conn = aiohttp.UnixConnector(socket_path)
        client = make_client_for_conn(NetEventAPI, conn)
        lock = asyncio.Lock()
        self.clients[socket_path] = (client, conn, lock)
        run_bg_task(
            self._call_client(
                client,
                conn,
                lock,
                "route_watch",
                self.network_event_receiver.has_default_route,
            )
        )

    async def subscription_DELETE(self, socket_path: str) -> None:
        if socket_path not in self.clients:
            return
        log.debug("removed subscription %s", socket_path)
        client, conn, lock = self.clients.pop(socket_path)
        async with lock:
            await conn.close()

    async def _call_client(self, client, conn, lock, meth_name, *args):
        async with lock:
            log.debug("_call_client %s %s", meth_name, conn.path)
            if conn.closed:
                log.debug("closed")
                return
            try:
                await getattr(client, meth_name).POST(*args)
            except aiohttp.ClientError:
                log.exception("call to %s on %s failed", meth_name, conn.path)

    def _call_clients(self, meth_name, *args):
        for client, conn, lock in self.clients.values():
            log.debug("creating _call_client task %s %s", conn.path, meth_name)
            run_bg_task(self._call_client(client, conn, lock, meth_name, *args))

    def apply_starting(self):
        super().apply_starting()
        self._call_clients("apply_starting")

    def apply_stopping(self):
        super().apply_stopping()
        self._call_clients("apply_stopping")

    def apply_error(self, stage):
        super().apply_error(stage)
        self._call_clients("apply_error", stage)

    def update_has_default_route(self, has_default_route):
        super().update_has_default_route(has_default_route)
        self._call_clients("route_watch", has_default_route)

    def _send_update(self, act, dev):
        with self.context.child("_send_update", "{} {}".format(act.name, dev.name)):
            # disable log - can contain PSK
            # log.debug("dev_info {} {}".format(dev.name, dev.config))
            dev_info = dev.netdev_info()
            self._call_clients("update_link", act, dev_info)

    def new_link(self, dev):
        super().new_link(dev)
        if dev.type == "wlan":
            self.maybe_start_install_wpasupplicant()
            state = self.wlan_support_install_state()
            if state == PackageInstallState.INSTALLING:
                self.pending_wlan_devices.add(dev)
                return
            elif state in [
                PackageInstallState.FAILED,
                PackageInstallState.NOT_AVAILABLE,
            ]:
                return
            # PackageInstallState.DONE falls through
        self._send_update(LinkAction.NEW, dev)

    def update_link(self, dev):
        super().update_link(dev)
        self._send_update(LinkAction.CHANGE, dev)

    def del_link(self, dev):
        super().del_link(dev)
        self._send_update(LinkAction.DEL, dev)

    async def set_static_config_POST(
        self, dev_name: str, ip_version: int, static_config: StaticConfig
    ) -> None:
        self.set_static_config(dev_name, ip_version, static_config)

    async def enable_dhcp_POST(self, dev_name: str, ip_version: int) -> None:
        self.enable_dhcp(dev_name, ip_version)

    async def disable_POST(self, dev_name: str, ip_version: int) -> None:
        self.disable_network(dev_name, ip_version)

    async def vlan_PUT(self, dev_name: str, vlan_id: int) -> None:
        self.add_vlan(dev_name, vlan_id)

    async def add_or_edit_bond_POST(
        self, existing_name: Optional[str], new_name: str, bond_config: BondConfig
    ) -> None:
        self.add_or_update_bond(existing_name, new_name, bond_config)

    async def set_wlan_POST(self, dev_name: str, wlan: WLANConfig) -> None:
        self.set_wlan(dev_name, wlan)

    async def start_scan_POST(self, dev_name: str) -> None:
        self.start_scan(dev_name)

    async def delete_POST(self, dev_name: str) -> None:
        self.delete_link(dev_name)

    async def info_GET(self, dev_name: str) -> str:
        return await self.get_info_for_netdev(dev_name)

    async def has_network_GET(self) -> bool:
        return self.model.has_network
