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


# Non-latin keyboard layouts that are handled in a uniform way
standard_non_latin_layouts = set(
    ('af', 'am', 'ara', 'ben', 'bd', 'bg', 'bt', 'by', 'et', 'ge',
     'gh', 'gr', 'guj', 'guru', 'il', 'in', 'iq', 'ir', 'iku', 'kan',
     'kh', 'kz', 'la', 'lao', 'lk', 'kg', 'ma', 'mk', 'mm', 'mn', 'mv',
     'mal', 'np', 'ori', 'pk', 'ru', 'scc', 'sy', 'syr', 'tel', 'th',
     'tj', 'tam', 'tib', 'ua', 'ug', 'uz')
)


def latinizable(layout_code, variant_code):
    """
    If this setting does not allow the typing of latin characters,
    return a setting that can be switched to one that can.
    """
    if layout_code == 'rs':
        if variant_code.startswith('latin'):
            return None
        else:
            if variant_code == 'yz':
                new_variant_code = 'latinyz'
            elif variant_code == 'alternatequotes':
                new_variant_code = 'latinalternatequotes'
            else:
                new_variant_code = 'latin'
            return 'rs,rs', new_variant_code + ',' + variant_code
    elif layout_code == 'jp':
        if variant_code in ('106', 'common', 'OADG109A', 'nicola_f_bs', ''):
            return None
        else:
            return 'jp,jp', ',' + variant_code
    elif layout_code == 'lt':
        if variant_code == 'us':
            return 'lt,lt', 'us,'
        else:
            return 'lt,lt', variant_code + ',us'
    elif layout_code == 'me':
        if variant_code == 'basic' or variant_code.startswith('latin'):
            return None
        else:
            return 'me,me', variant_code + ',us'
    elif layout_code in standard_non_latin_layouts:
        return 'us,' + layout_code, ',' + variant_code
    else:
        return None


def for_ui(setting):
    """
    Attempt to guess a setting the user chose which resulted in the
    current config.  Basically the inverse of latinizable().
    """
    if ',' in setting.layout:
        layout1, layout2 = setting.layout.split(',', 1)
    else:
        layout1, layout2 = setting.layout, ''
    if ',' in setting.variant:
        variant1, variant2 = setting.variant.split(',', 1)
    else:
        variant1, variant2 = setting.variant, ''
    if setting.layout == 'lt,lt':
        layout = layout1
        variant = variant1
    elif setting.layout in ('rs,rs', 'us,rs', 'jp,jp', 'us,jp'):
        layout = layout2
        variant = variant2
    elif layout1 == 'us' and layout2 in standard_non_latin_layouts:
        layout = layout2
        variant = variant2
    elif ',' in setting.layout:
        # Something unrecognized
        layout = 'us'
        variant = ''
    else:
        return setting
    return KeyboardSetting(
        layout=layout, variant=variant, toggle=setting.toggle)


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
        return for_ui(self.model.setting)

    async def POST(self, data: KeyboardSetting):
        new = latinizable(data.layout, data.variant)
        if new is not None:
            data = KeyboardSetting(new[0], new[1], data.toggle)
        self.model.setting = data
        self.configured()

    async def needs_toggle_GET(self, layout_code: str,
                               variant_code: str) -> bool:
        return latinizable(layout_code, variant_code) is not None

    async def steps_GET(self, index: Optional[str]) -> AnyStep:
        if self.pc105_steps is None:
            path = os.path.join(self._kbds_dir, 'pc105.json')
            with open(path) as fp:
                self.pc105_steps = self.serializer.from_json(
                    Dict[str, AnyStep], fp.read())
        if index is None:
            index = "0"
        return self.pc105_steps[index]
