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

import logging
import re
import os

import yaml

from subiquity.common.resources import resource_path
from subiquity.common.types import KeyboardSetting

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


class KeyboardModel:

    def __init__(self, root):
        self.config_path = os.path.join(
            root, 'etc', 'default', 'keyboard')
        self.layout_for_lang = self.load_layout_suggestions()
        if os.path.exists(self.config_path):
            self.default_setting = from_config_file(self.config_path)
        else:
            self.default_setting = self.layout_for_lang['en_US.UTF-8']
        self._setting = None

    @property
    def setting(self):
        if self._setting is None:
            return self.default_setting
        return self._setting

    @setting.setter
    def setting(self, value):
        self._setting = value

    def render_config_file(self):
        options = ""
        if self.setting.toggle:
            options = "grp:" + self.setting.toggle
        return etc_default_keyboard_template.format(
            layout=self.setting.layout,
            variant=self.setting.variant,
            options=options)

    def render(self):
        return {
            'write_files': {
                'etc_default_keyboard': {
                    'path': 'etc/default/keyboard',
                    'content': self.render_config_file(),
                    'permissions': 0o644,
                    },
                },
            }

    def setting_for_lang(self, lang):
        if self._setting is not None:
            return self._setting
        layout = self.layout_for_lang.get(lang, None)
        if layout is None:
            return self.default_setting
        return layout

    def load_layout_suggestions(self, path=None):
        if path is None:
            path = resource_path('kbds') + '/keyboard-configuration.yaml'

        with open(path) as fp:
            data = yaml.safe_load(fp)

        ret = {}
        for k, v in data.items():
            ret[k] = KeyboardSetting(**v)
        return ret
