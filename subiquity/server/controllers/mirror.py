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
import logging

from curtin.config import merge_config

from subiquitycore.async_helpers import CheckedSingleInstanceTask
from subiquitycore.context import with_context
from subiquitycore.geoip import GeoIP

from subiquity.common.apidef import API
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.mirror')


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
        self.lookup_task = CheckedSingleInstanceTask(self.lookup)
        self.app.hub.subscribe('network-up', self.maybe_start_check)
        self.app.hub.subscribe('network-proxy-set', self.maybe_start_check)

    def load_autoinstall_data(self, data):
        if data is None:
            return
        use_geoip = data.pop('geoip', True)
        merge_config(self.model.config, data)
        self.geoip_enabled = use_geoip and self.model.is_default()

    @with_context()
    async def apply_autoinstall_config(self, context):
        if not self.geoip_enabled:
            return
        if not self.lookup_task.has_started():
            return
        try:
            with context.child('waiting'):
                await asyncio.wait_for(self.lookup_task.wait(), 10)
        except asyncio.TimeoutError:
            pass

    def maybe_start_check(self):
        if not self.geoip_enabled:
            return
        # FIXME Q to mwhudson: there are multiple triggers for
        # maybe_start_check, should we not use the cached result if asked again?
        self.lookup_task.maybe_start_sync()

    @with_context()
    async def lookup(self, context):
        geoip = GeoIP()
        try:
            await geoip.lookup()
        except RuntimeError as re:
            log.debug(re)
            return
        self.model.set_country(geoip.get_country_code())

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
