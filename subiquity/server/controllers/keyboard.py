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

import logging
from typing import Dict, Optional
import os

import attr

from subiquitycore.context import with_context

from subiquity.common.apidef import API
from subiquity.common.keyboard import set_keyboard
from subiquity.common.serialize import Serializer
from subiquity.common.types import (
    AnyStep,
    KeyboardSetting,
    )
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.keyboard')


class KeyboardController(SubiquityController):

    endpoint = API.keyboard

    autoinstall_key = model_name = "keyboard"
    autoinstall_schema = {
        'type': 'object',
        'properties': {
            'layout': {'type': 'string'},
            'variant': {'type': 'string'},
            'toggle': {'type': ['string', 'null']},
            },
        'required': ['layout'],
        'additionalProperties': False,
        }

    def __init__(self, app):
        self._kbds_dir = os.path.join(os.environ.get("SNAP", '.'), 'kbds')
        self.serializer = Serializer(compact=True)
        self.pc105_steps = None
        self.needs_set_keyboard = False
        super().__init__(app)

    def load_autoinstall_data(self, data):
        if data is None:
            return
        setting = KeyboardSetting(**data)
        if self.model.setting != setting:
            self.needs_set_keyboard = True
        self.model.setting = setting

    @with_context()
    async def apply_autoinstall_config(self, context):
        if self.needs_set_keyboard:
            await set_keyboard(
                self.app.root, self.model.setting, self.opts.dry_run)

    def make_autoinstall(self):
        return attr.asdict(self.model.setting)

    async def GET(self) -> KeyboardSetting:
        return self.model.setting

    async def POST(self, data: KeyboardSetting):
        self.model.setting = data
        self.configured()

    async def steps_GET(self, index: Optional[str]) -> AnyStep:
        if self.pc105_steps is None:
            path = os.path.join(self._kbds_dir, 'pc105.json')
            with open(path) as fp:
                self.pc105_steps = self.serializer.from_json(
                    Dict[str, AnyStep], fp.read())
        if index is None:
            index = "0"
        return self.pc105_steps[index]
