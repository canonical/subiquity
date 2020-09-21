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
import re

from subiquitycore.utils import arun_command

from subiquity.common.types import KeyboardSetting


etc_default_keyboard_template = """\
# KEYBOARD CONFIGURATION FILE

# Consult the keyboard(5) manual page.

XKBMODEL="pc105"
XKBLAYOUT="{layout}"
XKBVARIANT="{variant}"
XKBOPTIONS="{options}"

BACKSPACE="guess"
"""


def from_config_file(config_file):
    with open(config_file) as fp:
        content = fp.read()

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
    return KeyboardSetting(layout=XKBLAYOUT, variant=XKBVARIANT, toggle=toggle)


def render(setting):
    options = ""
    if setting.toggle:
        options = "grp:" + setting.toggle
    return etc_default_keyboard_template.format(
        layout=setting.layout,
        variant=setting.variant,
        options=options)


async def set_keyboard(root, setting, dry_run):
    path = os.path.join(root, 'etc', 'default', 'keyboard')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fp:
        fp.write(render(setting))
    cmds = [
        ['setupcon', '--save', '--force', '--keyboard-only'],
        ['/snap/bin/subiquity.subiquity-loadkeys'],
        ]
    if dry_run:
        scale = os.environ.get('SUBIQUITY_REPLAY_TIMESCALE', "1")
        cmds = [['sleep', str(1/float(scale))]]
    for cmd in cmds:
        await arun_command(cmd)
