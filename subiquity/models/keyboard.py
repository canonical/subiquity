
import logging
import os
import re

from lxml import etree

from subiquitycore.utils import run_command

log = logging.getLogger("subiquity.models.keyboard")

class Layout:
    def __init__(self, code, desc):
        self.code = code
        self.desc = desc
        self.variants = []
        self.languages = set()
    def __repr__(self):
        return "Layout({}, {}) {} {}".format(self.code, self.desc, self.variants, self.languages)


class Variant:
    def __init__(self, code, desc):
        self.code = code
        self.desc = desc
        self.languages = set()
    def __repr__(self):
        return "Variant({}, {}) {}".format(self.code, self.desc, self.languages)


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
        self.layouts = [] # Layout objects
        self.root = root
        self.layout = 'us'
        self.variant = ''
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

    def parse(self, fname):
        t = etree.parse(fname)
        for layout_elem in t.xpath("//layoutList/layout"):
            c = layout_elem.find("configItem")
            code = c.find("name").text
            description = c.find("description").text
            layout = Layout(code, description)
            for lang in c.xpath("languageList/iso639Id/text()"):
                layout.languages.add(lang)
            for v in layout_elem.xpath("variantList/variant/configItem"):
                var = Variant(v.find("name").text, v.find("description").text)
                layout.variants.append(var)
                for lang in v.xpath("languageList/iso639Id/text()"):
                    var.languages.add(lang)
            self.layouts.append(layout)

    def lookup(self, code):
        if ':' in code:
            layout_code, var_code = code.split(":", 1)
        else:
            layout_code, var_code = code, None
        for layout in self.layouts:
            if layout.code == layout_code:
                if var_code is None:
                    return layout, None
                for variant in layout.variants:
                    if variant.code == var_code:
                        return layout, variant
        raise Exception("%s not found" % (code,))

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
