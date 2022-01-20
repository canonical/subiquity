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
import copy
import logging
from typing import List

from curtin.config import merge_config

from subiquitycore.async_helpers import SingleInstanceTask
from subiquitycore.context import with_context

from subiquity.common.apidef import API
from subiquity.server.apt import get_apt_configurer
from subiquity.server.controller import SubiquityController
from subiquity.server.types import InstallerChannels

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
            'disable_components': {
                'type': 'array',
                'items': {
                    'type': 'string',
                    'enum': ['universe', 'multiverse', 'restricted',
                             'contrib', 'non-free']
                }
            },
            "preferences": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "package": {
                            "type": "string",
                        },
                        "pin": {
                            "type": "string",
                        },
                        "pin-priority": {
                            "type": "integer",
                        },
                    },
                    "required": [
                        "package",
                        "pin",
                        "pin-priority",
                    ],
                }
            }
        }
    }
    model_name = "mirror"

    def __init__(self, app):
        super().__init__(app)
        self.geoip_enabled = True
        self.app.hub.subscribe(InstallerChannels.GEOIP, self.on_geoip)
        self.app.hub.subscribe(
            (InstallerChannels.CONFIGURED, 'source'), self.on_source)
        self.cc_event = asyncio.Event()
        self.configured_once = False
        self._apt_config_key = None
        self._apply_apt_config_task = SingleInstanceTask(
            self._apply_apt_config)
        self.apt_configurer = None

    def load_autoinstall_data(self, data):
        if data is None:
            return
        geoip = data.pop('geoip', True)
        merge_config(self.model.config, data)
        self.geoip_enabled = geoip and self.model.mirror_is_default()

    @with_context()
    async def apply_autoinstall_config(self, context):
        if not self.geoip_enabled:
            return
        try:
            with context.child('waiting'):
                await asyncio.wait_for(self.cc_event.wait(), 10)
        except asyncio.TimeoutError:
            pass

    def on_geoip(self):
        if self.geoip_enabled:
            self.model.set_country(self.app.geoip.countrycode)
        self.cc_event.set()

    def on_source(self):
        if self.configured_once:
            self._apply_apt_config_task.start_sync()

    def serialize(self):
        return self.model.get_mirror()

    def deserialize(self, data):
        self.model.set_mirror(data)

    def make_autoinstall(self):
        r = copy.deepcopy(self.model.config)
        r['geoip'] = self.geoip_enabled
        return r

    async def configured(self):
        await super().configured()
        self.configured_once = True
        self._apply_apt_config_task.start_sync()

    async def _apply_apt_config(self):
        # if self.apt_configurer is not None:
        # FIXME disabled until we can sort out umount
        # await self.apt_configurer.cleanup()
        self.apt_configurer = get_apt_configurer(
            self.app, self.app.controllers.Source.source_path)
        await self.apt_configurer.apply_apt_config(self.context)

    async def wait_config(self):
        await self._apply_apt_config_task.wait()
        return self.apt_configurer

    async def GET(self) -> str:
        return self.model.get_mirror()

    async def POST(self, data: str):
        self.model.set_mirror(data)
        await self.configured()

    async def disable_components_GET(self) -> List[str]:
        return self.model.config.get('disable_components', [])

    async def disable_components_POST(self, data: List[str]):
        self.model.config['disable_components'] = data
