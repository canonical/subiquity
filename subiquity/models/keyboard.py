
from collections import defaultdict
import gzip
import io
import logging
import os
import re

from subiquitycore.utils import run_command

log = logging.getLogger("subiquity.models.keyboard")

etc_default_keyboard_template = """\
# KEYBOARD CONFIGURATION FILE

# Consult the keyboard(5) manual page.

XKBMODEL="pc105"
XKBLAYOUT="{layout}"
XKBVARIANT="{variant}"
XKBOPTIONS=""

BACKSPACE="guess"
"""

class KeyboardModel:
    def __init__(self, root):
        self.root = root
        self.layout = 'us'
        self.variant = ''
        self._kbnames_file = os.path.join(os.environ.get("SNAP", '.'), 'kbdnames.gz')
        self._clear()
        if os.path.exists(self.config_path):
            content = open(self.config_path).read()
            pat_tmpl = '(?m)^\s*%s=(.*)$'
            log.debug("%r", content)
            layout_match = re.search(pat_tmpl%("XKBLAYOUT",), content)
            if layout_match:
                log.debug("%s", layout_match)
                self.layout = layout_match.group(1).strip('"')
            variant_match = re.search(pat_tmpl%("XKBVARIANT",), content)
            if variant_match:
                log.debug("%s", variant_match)
                self.variant = variant_match.group(1).strip('"')
                if self.variant == '':
                    self.variant = None

    @property
    def config_path(self):
        return os.path.join(self.root, 'etc', 'default', 'keyboard')

    @property
    def config_content(self):
        return etc_default_keyboard_template.format(layout=self.layout, variant=self.variant)

    def has_language(self, code):
        self.load_language(code)
        return bool(self.layouts)

    def load_language(self, code):
        if code == self.current_lang:
            return

        self._clear()

        raw = gzip.open(self._kbnames_file)
        try:
            with io.TextIOWrapper(raw) as kbdnames:
                self._load_file(code, kbdnames)
        finally:
            raw.close()
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
            return self.layouts.get(layout_code, '?'), self._variants.get(variant_code, '?')
        else:
            return self.layouts.get(code, '?'), None

    def set_keyboard(self, layout, variant):
        path = os.path.join(self.config_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.layout = layout
        self.variant = variant
        with open(path, 'w') as fp:
            fp.write(self.config_content)
        if self.root == '/':
            run_command(['setupcon', '--save', '--force'])


def main(args):
    lang = args[1]
    m = KeyboardModel()
    m.parse("/usr/share/X11/xkb/rules/base.xml")
    for keyboard in m.keyboards:
        if lang in keyboard.languages:
            print(keyboard.code, keyboard.languages)
        for name, _, langs in keyboard.variants:
            if lang in langs:
                print(keyboard.code, name, langs)


if __name__ == "__main__":
    import sys
    main(sys.argv)
