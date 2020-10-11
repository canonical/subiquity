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

log = logging.getLogger('subiquity.server.controllers.proxy')


class ProxyController(SubiquityController):

    endpoint = API.proxy

    autoinstall_key = model_name = "proxy"
    autoinstall_schema = {
        'type': ['string', 'null'],
        'format': 'uri',
        }

    def load_autoinstall_data(self, data):
        if data is not None:
            self.model.proxy = data

    def start(self):
        if self.model.proxy:
            os.environ['http_proxy'] = os.environ['https_proxy'] = \
              self.model.proxy
            self.signal.emit_signal('network-proxy-set')

    @with_context()
    async def apply_autoinstall_config(self, context=None):
        # XXX want to wait until signal sent by .start() has been seen
        # by everything; don't have a way to do that today.
        pass

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
        self.signal.emit_signal('network-proxy-set')
        self.configured()
