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

import os
from typing import Dict

from subiquity.common.serialize import Serializer
from subiquity.common.types import (
    AnyStep,
    KeyboardLayout,
    KeyboardSetting,
    )


# Non-latin keyboard layouts that are handled in a uniform way
standard_non_latin_layouts = set(
    ('af', 'am', 'ara', 'ben', 'bd', 'bg', 'bt', 'by', 'et', 'ge',
     'gh', 'gr', 'guj', 'guru', 'il', 'in', 'iq', 'ir', 'iku', 'kan',
     'kh', 'kz', 'la', 'lao', 'lk', 'kg', 'ma', 'mk', 'mm', 'mn', 'mv',
     'mal', 'np', 'ori', 'pk', 'ru', 'scc', 'sy', 'syr', 'tel', 'th',
     'tj', 'tam', 'tib', 'ua', 'ug', 'uz')
)


def latinizable(setting):
    """
    If this setting does not allow the typing of latin characters,
    return a setting that can be switched to one that can.
    """
    if setting.layout == 'rs':
        if setting.variant.startswith('latin'):
            return setting
        else:
            if setting.variant == 'yz':
                new_variant = 'latinyz'
            elif setting.variant == 'alternatequotes':
                new_variant = 'latinalternatequotes'
            else:
                new_variant = 'latin'
            return KeyboardSetting(layout='rs,rs',
                                   variant=(new_variant +
                                            ',' + setting.variant))
    elif setting.layout == 'jp':
        if setting.variant in ('106', 'common', 'OADG109A',
                               'nicola_f_bs', ''):
            return setting
        else:
            return KeyboardSetting(layout='jp,jp',
                                   variant=',' + setting.variant)
    elif setting.layout == 'lt':
        if setting.variant == 'us':
            return KeyboardSetting(layout='lt,lt', variant='us,')
        else:
            return KeyboardSetting(layout='lt,lt',
                                   variant=setting.variant + ',us')
    elif setting.layout == 'me':
        if setting.variant == 'basic' or setting.variant.startswith('latin'):
            return setting
        else:
            return KeyboardSetting(layout='me,me',
                                   variant=setting.variant + ',us')
    elif setting.layout in standard_non_latin_layouts:
        return KeyboardSetting(layout='us,' + setting.layout,
                               variant=',' + setting.variant)
    else:
        return setting


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
    return KeyboardSetting(layout=layout, variant=variant)


class KeyboardList:

    def __init__(self):
        self._kbnames_dir = os.path.join(os.environ.get("SNAP", '.'), 'kbds')
        self.serializer = Serializer(compact=True)
        self._clear()

    def _file_for_lang(self, code):
        return os.path.join(self._kbnames_dir, code + '.jsonl')

    def has_language(self, code):
        return os.path.exists(self._file_for_lang(code))

    def load_language(self, code):
        if code == self.current_lang:
            return

        self._clear()

        with open(self._file_for_lang(code)) as kbdnames:
            self.layouts = [
                self.serializer.from_json(KeyboardLayout, line)
                for line in kbdnames
                ]
        self.current_lang = code

    def _clear(self):
        self.current_lang = None
        self.layouts = []

    def load_pc105(self):
        path = os.path.join(self._kbnames_dir, 'pc105.json')
        with open(path) as fp:
            return self.serializer.from_json(Dict[str, AnyStep], fp.read())
