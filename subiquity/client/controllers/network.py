# Copyright 2020 Canonical, Ltd.
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
import shutil
import tempfile
from typing import List, Optional

from aiohttp import web

from subiquitycore.controllers.network import NetworkAnswersMixin
from subiquitycore.models.network import (
    BondConfig,
    NetDevInfo,
    StaticConfig,
    WLANConfig,
    )
from subiquitycore.ui.views.network import NetworkView

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.api.server import make_server_at_path
from subiquity.common.apidef import LinkAction, NetEventAPI
from subiquity.common.types import (
    ErrorReportKind,
    WLANSupportInstallState,
    )

log = logging.getLogger('subiquity.client.controllers.network')


class NetworkController(SubiquityTuiController, NetworkAnswersMixin):

    endpoint_name = 'network'

    def __init__(self, app):
        super().__init__(app)
        self.view = None

    @web.middleware
    async def middleware(self, request, handler):
        resp = await handler(request)
        if resp.get('exception'):
            exc = resp['exception']
            log.debug(
                'request to {} crashed'.format(request.raw_path), exc_info=exc)
            self.app.make_apport_report(
                ErrorReportKind.NETWORK_CLIENT_FAIL,
                "request to {}".format(request.raw_path),
                exc=exc, interrupt=True)
        return resp

    async def update_link_POST(self, act: LinkAction,
                               info: NetDevInfo) -> None:
        if self.view is None:
            return
        if act == LinkAction.NEW:
            self.view.new_link(info)
        if act == LinkAction.CHANGE:
            self.view.update_link(info)
        if act == LinkAction.DEL:
            self.view.del_link(info)

    async def route_watch_POST(self, routes: List[int]) -> None:
        if self.view is not None:
            self.view.update_default_routes(routes)

    async def apply_starting_POST(self) -> None:
        if self.view is not None:
            self.view.show_apply_spinner()

    async def apply_stopping_POST(self) -> None:
        if self.view is not None:
            self.view.hide_apply_spinner()

    async def apply_error_POST(self, stage: str) -> None:
        if self.view is not None:
            self.view.show_network_error(stage)

    async def wlan_support_install_finished_POST(
            self, state: WLANSupportInstallState) -> None:
        if self.view:
            self.view.update_for_wlan_support_install_state(state.name)

    async def subscribe(self):
        self.tdir = tempfile.mkdtemp()
        self.sock_path = os.path.join(self.tdir, 'socket')
        self.site = await make_server_at_path(
            self.sock_path, NetEventAPI, self, middlewares=[self.middleware])
        await self.endpoint.subscription.PUT(self.sock_path)

    async def unsubscribe(self):
        await self.endpoint.subscription.DELETE(self.sock_path)
        await self.site.stop()
        shutil.rmtree(self.tdir)

    async def make_ui(self):
        network_status = await self.endpoint.GET()
        self.view = NetworkView(
            self, network_status.devices,
            network_status.wlan_support_install_state.name)
        await self.subscribe()
        return self.view

    def end_ui(self):
        if self.view is not None:
            self.view = None
            self.app.aio_loop.create_task(self.unsubscribe())

    def cancel(self):
        self.app.prev_screen()

    def done(self):
        self.app.next_screen(self.endpoint.POST())

    def set_static_config(self, dev_name: str, ip_version: int,
                          static_config: StaticConfig) -> None:
        self.app.aio_loop.create_task(
            self.endpoint.set_static_config.POST(
                dev_name, ip_version, static_config))

    def enable_dhcp(self, dev_name, ip_version: int) -> None:
        self.app.aio_loop.create_task(
            self.endpoint.enable_dhcp.POST(dev_name, ip_version))

    def disable_network(self, dev_name: str, ip_version: int) -> None:
        self.app.aio_loop.create_task(
            self.endpoint.disable.POST(dev_name, ip_version))

    def add_vlan(self, dev_name: str, vlan_id: int):
        self.app.aio_loop.create_task(
            self.endpoint.vlan.PUT(dev_name, vlan_id))

    def set_wlan(self, dev_name: str, wlan: WLANConfig) -> None:
        self.app.aio_loop.create_task(
            self.endpoint.set_wlan.POST(dev_name, wlan))

    def start_scan(self, dev_name: str) -> None:
        self.app.aio_loop.create_task(
            self.endpoint.start_scan.POST(dev_name))

    def delete_link(self, dev_name: str):
        self.app.aio_loop.create_task(self.endpoint.delete.POST(dev_name))

    def add_or_update_bond(self, existing_name: Optional[str],
                           new_name: str, new_info: BondConfig) -> None:
        self.app.aio_loop.create_task(
            self.endpoint.add_or_edit_bond.POST(
                existing_name, new_name, new_info))

    async def get_info_for_netdev(self, dev_name: str) -> str:
        return await self.endpoint.info.GET(dev_name)
