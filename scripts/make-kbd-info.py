#!/usr/bin/python3

from collections import defaultdict
import os
import shutil
import subprocess

from subiquity.common.serialize import Serializer
from subiquity.common.types import (
    KeyboardLayout,
    KeyboardVariant,
    )

tdir = os.path.join(os.environ.get('SNAPCRAFT_PART_INSTALL', '.'), 'kbds')
if os.path.exists(tdir):
    shutil.rmtree(tdir)
os.mkdir(tdir)

p = subprocess.Popen(
    ['/usr/share/console-setup/kbdnames-maker',
     '/usr/share/console-setup/KeyboardNames.pl'],
    stdout=subprocess.PIPE, encoding='utf-8')


lang_to_layouts = defaultdict(dict)


for line in p.stdout:
    lang, element, name, value = line.strip().split("*", 3)
    if element == 'model':
        continue
    elif element == 'variant':
        layout = lang_to_layouts[lang][name]
        variant, value = value.split('*', 1)
        if not layout.variants and variant != "":
            raise Exception(
                "subiquity assumes all keyboard layouts have the default "
                "variant at index 0!")
        layout.variants.append(KeyboardVariant(code=variant, name=value))
    elif element == 'layout':
        lang_to_layouts[lang][name] = KeyboardLayout(
            code=name, name=value, variants=[])


s = Serializer(compact=True)


for lang, layouts in lang_to_layouts.items():
    if 'us' not in layouts:
        raise Exception("subiquity assumes there is always a us keyboard "
                        "layout")
    outpath = os.path.join(tdir, lang + '.jsonl')
    with open(outpath, 'w') as out:
        for layout in layouts.values():
            if len(layout.variants) == 0:
                raise Exception(
                    "subiquity assumes all keyboard layouts have at least one "
                    "variant!")
            out.write(s.to_json(KeyboardLayout, layout) + "\n")
