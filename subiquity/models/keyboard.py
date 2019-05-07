
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
    variant = attr.ib(default='')
    toggle = attr.ib(default=None)

    def render(self):
        options = ""
        if self.toggle:
            options = "grp:" + self.toggle
        return etc_default_keyboard_template.format(
            layout=self.layout, variant=self.variant, options=options)

    def latinizable(self):
        """
        If this setting does not allow the typing of latin characters,
        return a setting that can be switched to one that can.
        """
        if self.layout == 'rs':
            if self.variant.startswith('latin'):
                return self
            else:
                if self.variant == 'yz':
                    new_variant = 'latinyz'
                elif self.variant == 'alternatequotes':
                    new_variant = 'latinalternatequotes'
                else:
                    new_variant = 'latin'
                return KeyboardSetting(layout='rs,rs',
                                       variant=(new_variant +
                                                ',' + self.variant))
        elif self.layout == 'jp':
            if self.variant in ('106', 'common', 'OADG109A',
                                'nicola_f_bs', ''):
                return self
            else:
                return KeyboardSetting(layout='jp,jp',
                                       variant=',' + self.variant)
        elif self.layout == 'lt':
            if self.variant == 'us':
                return KeyboardSetting(layout='lt,lt', variant='us,')
            else:
                return KeyboardSetting(layout='lt,lt',
                                       variant=self.variant + ',us')
        elif self.layout == 'me':
            if self.variant == 'basic' or self.variant.startswith('latin'):
                return self
            else:
                return KeyboardSetting(layout='me,me',
                                       variant=self.variant + ',us')
        elif self.layout in standard_non_latin_layouts:
            return KeyboardSetting(layout='us,' + self.layout,
                                   variant=',' + self.variant)
        else:
            return self

    @classmethod
    def from_config_file(cls, config_file):
        content = open(config_file).read()

        def optval(opt, default):
            match = re.search(r'(?m)^\s*%s=(.*)$' % (opt,), content)
            if match:
                r = match.group(1).strip('"')
                if r != '':
                    return r
            return default
        XKBLAYOUT = optval("XKBLAYOUT", "us")
        XKBVARIANT = optval("XKBVARIANT", "")
        XKBOPTIONS = optval("XKBOPTIONS", "")
        toggle = None
        for option in XKBOPTIONS.split(','):
            if option.startswith('grp:'):
                toggle = option[4:]
        return cls(layout=XKBLAYOUT, variant=XKBVARIANT, toggle=toggle)

    def for_ui(self):
        """
        Attempt to guess a setting the user chose which resulted in the
        current config.  Basically the inverse of latinizable().
        """
        if ',' in self.layout:
            layout1, layout2 = self.layout.split(',', 1)
        else:
            layout1, layout2 = self.layout, ''
        if ',' in self.variant:
            variant1, variant2 = self.variant.split(',', 1)
        else:
            variant1, variant2 = self.variant, ''
        if self.layout == 'lt,lt':
            layout = layout1
            variant = variant1
        elif self.layout in ('rs,rs', 'us,rs', 'jp,jp', 'us,jp'):
            layout = layout2
            variant = variant2
        elif layout1 == 'us' and layout2 in standard_non_latin_layouts:
            layout = layout2
            variant = variant2
        elif ',' in self.layout:
            # Something unrecognized
            layout = 'us'
            variant = ''
        else:
            return self
        return KeyboardSetting(layout=layout, variant=variant)


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
        self._kbnames_file = os.path.join(os.environ.get("SNAP", '.'),
                                          'kbdnames.txt')
        self._clear()
        if os.path.exists(self.config_path):
            self.setting = KeyboardSetting.from_config_file(self.config_path)
        else:
            self.setting = KeyboardSetting(layout='us')

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
            layout = self.layouts.get(layout_code, '?')
            variant = self.variants.get(layout_code, {}).get(variant_code, '?')
            return (layout, variant)
        else:
            return self.layouts.get(code, '?'), None

    def set_keyboard(self, setting):
        path = self.config_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as fp:
            fp.write(self.setting.render())
        if setting != self.setting:
            self.setting = setting
            if self.root == '/':
                run_command([
                    'setupcon', '--save', '--force', '--keyboard-only'])
                run_command(['/snap/bin/subiquity.subiquity-loadkeys'])
            else:
                scale = os.environ.get('SUBIQUITY_REPLAY_TIMESCALE', "1")
                run_command(['sleep', str(1/float(scale))])

    def render(self):
        return {
            'write_files': {
                'etc_default_keyboard': {
                    'path': 'etc/default/keyboard',
                    'content': self.setting.render(),
                    'permissions': 0o644,
                    },
                },
            }
