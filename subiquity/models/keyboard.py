
from collections import defaultdict
import logging
import os
import re

import attr

from subiquitycore.utils import run_command

log = logging.getLogger("subiquity.models.keyboard")

etc_default_keyboard_template = """\
# KEYBOARD CONFIGURATION FILE

# Consult the keyboard(5) manual page.

XKBMODEL="pc105"
XKBLAYOUT="{layout}"
XKBVARIANT="{variant}"
XKBOPTIONS="{options}"

BACKSPACE="guess"
"""

@attr.s
class KeyboardSetting:
    layout = attr.ib()
    variant = attr.ib(default=None)
    toggle = attr.ib(default=None)

    def render(self):
        options = ""
        if self.toggle:
            options = "grp:" + self.toggle
        variant = self.variant
        if variant is None:
            variant = ''
        return etc_default_keyboard_template.format(
            layout=self.layout, variant=variant, options=options)

    @classmethod
    def from_config(cls, XKBLAYOUT, XKBVARIANT, XKBOPTIONS):
        toggle = None
        if ',' in XKBLAYOUT:
            layout1, layout2 = XKBLAYOUT.split(',', 1)
            for option in XKBOPTIONS.split(','):
                if option.startswith('grp:'):
                    toggle = option[4:]
        else:
            layout1, layout2 = XKBLAYOUT, ''
        if ',' in XKBVARIANT:
            variant1, variant2 = XKBVARIANT.split(',', 1)
        else:
            variant1, variant2 = XKBVARIANT, ''
        if XKBLAYOUT == 'lt,lt':
            layout = layout1
            variant = variant1
        elif XKBLAYOUT in ('rs,rs', 'us,rs', 'jp,jp', 'us,jp'):
            layout = layout2
            variant = variant2
        elif layout1 == 'us' and layout2 in standard_non_latin_layouts:
            layout = layout2
            variant = variant2
        elif ',' in XKBLAYOUT:
            # Something unrecognized
            layout = 'us'
            variant = ''
        else:
            layout = XKBLAYOUT
            variant = XKBVARIANT
        return cls(layout=layout, variant=variant, toggle=toggle)


# Non-latin keyboard layouts that are handled in a uniform way
standard_non_latin_layouts = set(
    ('af', 'am', 'ara', 'ben', 'bd', 'bg', 'bt', 'by', 'et', 'ge',
    'gh', 'gr', 'guj', 'guru', 'il', ''in'', 'iq', 'ir', 'iku', 'kan',
    'kh', 'kz', 'la', 'lao', 'lk', 'kg', 'ma', 'mk', 'mm', 'mn', 'mv',
    'mal', 'np', 'ori', 'pk', 'ru', 'scc', 'sy', 'syr', 'tel', 'th',
    'tj', 'tam', 'tib', 'ua', 'ug', 'uz')
    )


class KeyboardModel:
    def __init__(self, root):
        self.root = root
        self.setting = KeyboardSetting(layout='us')
        self._kbnames_file = os.path.join(os.environ.get("SNAP", '.'), 'kbdnames.txt')
        self._clear()
        if os.path.exists(self.config_path):
            content = open(self.config_path).read()
            def optval(opt, default):
                match = re.search('(?m)^\s*%s=(.*)$'%(opt,), content)
                if match:
                    r = match.group(1).strip('"')
                    if r != '':
                        return r
                return default
            XKBLAYOUT = optval("XKBLAYOUT", "us")
            XKBVARIANT = optval("XKBVARIANT", "")
            XKBOPTIONS = optval("XKBOPTIONS", "")
            self.setting = KeyboardSetting.from_config(XKBLAYOUT, XKBVARIANT, XKBOPTIONS)

    @property
    def config_path(self):
        return os.path.join(self.root, 'etc', 'default', 'keyboard')

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
            return self.layouts.get(layout_code, '?'), self.variants.get(layout_code, {}).get(variant_code, '?')
        else:
            return self.layouts.get(code, '?'), None

    def set_keyboard(self, setting):
        path = self.config_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.setting = setting
        with open(path, 'w') as fp:
            fp.write(self.setting.render())
        if self.root == '/':
            run_command(['setupcon', '--save', '--force'])
            run_command(['/snap/bin/subiquity.subiquity-loadkeys'])
        else:
            run_command(['sleep', '1'])

    def adjust_setting(self, setting):
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
                return KeyboardSetting(layout='rs,rs', variant=new_variant + ',' + setting.variant)
        elif setting.layout == 'jp':
            if setting.variant in ('106', 'common', 'OADG109A', 'nicola_f_bs', ''):
                return setting
            else:
                return KeyboardSetting(layout='jp,jp', variant=',' + setting.variant)
        elif setting.layout == 'lt':
            if setting.variant == 'us':
                return KeyboardSetting(layout='lt,lt', variant='us,')
            else:
                return KeyboardSetting(layout='lt,lt', variant=setting.variant + ',us')
        elif setting.layout == 'me':
            if setting.variant == 'basic' or setting.variant.startswith('latin'):
                return setting
            else:
                return KeyboardSetting(layout='me,me', variant=setting.variant + ',us')
        elif setting.layout in standard_non_latin_layouts:
            return KeyboardSetting(layout='us,' + setting.layout, variant=',' + setting.variant)
        else:
            return setting
