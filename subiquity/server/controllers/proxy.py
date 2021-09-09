# Copyright 2018 Canonical, Ltd.
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

from subiquitycore.context import with_context

from subiquity.common.apidef import API
from subiquity.server.controller import SubiquityController
from subiquity.server.types import InstallerChannels

log = logging.getLogger('subiquity.server.controllers.proxy')


class ProxyController(SubiquityController):

    endpoint = API.proxy

    autoinstall_key = model_name = "proxy"
    autoinstall_schema = {
        'type': ['string', 'null'],
        'format': 'uri',
        }

    _set_task = None

    def load_autoinstall_data(self, data):
        if data is not None:
            self.model.proxy = data

    def start(self):
        if self.model.proxy:
            os.environ['http_proxy'] = os.environ['https_proxy'] = \
              self.model.proxy
            self._set_task = self.app.hub.broadcast(
                InstallerChannels.NETWORK_PROXY_SET)

    @with_context()
    async def apply_autoinstall_config(self, context=None):
        if self._set_task is not None:
            await self._set_task

    def serialize(self):
        return self.model.proxy

    def deserialize(self, data):
        self.model.proxy = data

    def make_autoinstall(self):
        return self.model.proxy

    async def GET(self) -> str:
        return self.model.proxy

    async def POST(self, data: str):
        self.model.proxy = data
        os.environ['http_proxy'] = os.environ['https_proxy'] = data
        self.app.hub.broadcast(InstallerChannels.NETWORK_PROXY_SET)
        self.configured()
