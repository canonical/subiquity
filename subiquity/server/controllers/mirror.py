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

import asyncio
import enum
import logging

from curtin.config import merge_config

from subiquitycore.async_helpers import SingleInstanceTask
from subiquitycore.context import with_context

from subiquity.common.apidef import API
from subiquity.common.geoip import GeoIP
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.mirror')


class CheckState(enum.IntEnum):
    NOT_STARTED = enum.auto()
    CHECKING = enum.auto()
    FAILED = enum.auto()
    DONE = enum.auto()


class MirrorController(SubiquityController):

    endpoint = API.mirror

    autoinstall_key = "apt"
    autoinstall_schema = {  # This is obviously incomplete.
        'type': 'object',
        'properties': {
            'preserve_sources_list': {'type': 'boolean'},
            'primary': {'type': 'array'},
            'geoip':  {'type': 'boolean'},
            'sources': {'type': 'object'},
            },
        }
    model_name = "mirror"

    def __init__(self, app):
        super().__init__(app)
        self.geoip_enabled = True
        self.check_state = CheckState.NOT_STARTED
        self.lookup_task = SingleInstanceTask(self.lookup)
        self.geoip = GeoIP()
        self.app.hub.subscribe('network-up', self.maybe_start_check)
        self.app.hub.subscribe('network-proxy-set', self.maybe_start_check)

    def load_autoinstall_data(self, data):
        if data is None:
            return
        geoip = data.pop('geoip', True)
        merge_config(self.model.config, data)
        self.geoip_enabled = geoip and self.model.is_default()

    @with_context()
    async def apply_autoinstall_config(self, context):
        if not self.geoip_enabled:
            return
        if self.lookup_task.task is None:
            return
        try:
            with context.child('waiting'):
                await asyncio.wait_for(self.lookup_task.wait(), 10)
        except asyncio.TimeoutError:
            pass

    def maybe_start_check(self):
        if not self.geoip_enabled:
            return
        if self.check_state != CheckState.DONE:
            self.check_state = CheckState.CHECKING
            self.lookup_task.start_sync()

    @with_context()
    async def lookup(self, context):
        if await self.geoip.lookup():
            cc = self.geoip.countrycode
            if cc:
                self.model.set_country(cc)
                self.check_state = CheckState.DONE
                return
        self.check_state = CheckState.FAILED

    def serialize(self):
        return self.model.get_mirror()

    def deserialize(self, data):
        self.model.set_mirror(data)

    def make_autoinstall(self):
        r = self.model.render()['apt']
        r['geoip'] = self.geoip_enabled
        return r

    async def GET(self) -> str:
        return self.model.get_mirror()

    async def POST(self, data: str):
        self.model.set_mirror(data)
        self.configured()
