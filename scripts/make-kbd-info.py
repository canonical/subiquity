#!/usr/bin/python3

from collections import defaultdict
import os
import shutil
import subprocess
import sys
from typing import Dict

from subiquity.common.serialize import Serializer
from subiquity.common.types import (
    AnyStep,
    KeyboardLayout,
    KeyboardVariant,
    StepPressKey,
    StepKeyPresent,
    )

sys.path.insert(0, os.path.dirname(__file__))

import pc105 # noqa


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


pc105tree = pc105.PC105Tree()
pc105tree.read_steps()

if '0' not in pc105tree.steps:
    raise Exception("subiquity assumes there is a step '0' in the pc105 steps")

for index, step in pc105tree.steps.items():
    if isinstance(step, StepPressKey):
        if len(step.symbols) == 0 or len(step.keycodes) == 0:
            raise Exception(f"step {index} {step} appears to be incomplete")
        for v in step.keycodes.values():
            if v not in pc105tree.steps:
                raise Exception(
                    f"step {index} {step} references missing step {v}")
    elif isinstance(step, StepKeyPresent):
        for v in step.yes, step.no:
            if v not in pc105tree.steps:
                raise Exception(
                    f"step {index} {step} references missing step {v}")

with open(os.path.join(tdir, 'pc105.json'), 'w') as out:
    out.write(s.to_json(Dict[str, AnyStep], pc105tree.steps))
