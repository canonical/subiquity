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

from collections import defaultdict
import os

from subiquity.common.types import KeyboardSetting


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
        self._kbnames_file = os.path.join(
            os.environ.get("SNAP", '.'),
            'kbdnames.txt')
        self._clear()

    def has_language(self, code):
        self.load_language(code)
        return bool(self.layouts)

    def load_language(self, code):
        if code == self.current_lang:
            return

        self._clear()

        with open(self._kbnames_file, encoding='utf-8') as kbdnames:
            self._load_file(code, kbdnames)
        self.current_lang = code

    def _clear(self):
        self.current_lang = None
        self.layouts = {}
        self.variants = defaultdict(dict)

    def _load_file(self, code, kbdnames):
        for line in kbdnames:
            line = line.rstrip('\n')
            got_lang, element, name, value = line.split("*", 3)
            if got_lang != code:
                continue

            if element == "layout":
                self.layouts[name] = value
            elif element == "variant":
                variantname, variantdesc = value.split("*", 1)
                self.variants[name][variantname] = variantdesc

    def lookup(self, code):
        if ':' in code:
            layout_code, variant_code = code.split(":", 1)
            layout = self.layouts.get(layout_code, '?')
            variant = self.variants.get(layout_code, {}).get(variant_code, '?')
            return (layout, variant)
        else:
            return self.layouts.get(code, '?'), None
