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
import os
import re

import yaml

from subiquity.common.resources import resource_path
from subiquity.common.serialize import Serializer
from subiquity.common.types import KeyboardLayout, KeyboardSetting

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


class InconsistentMultiLayoutError(ValueError):
    """Exception to raise when a multi layout has a different number of
    layouts and variants."""

    def __init__(self, layouts: str, variants: str) -> None:
        super().__init__(
            f'inconsistent multi-layout: layouts="{layouts}" variants="{variants}"'
        )


def from_config_file(config_file):
    with open(config_file) as fp:
        content = fp.read()

    def optval(opt, default):
        match = re.search(r"(?m)^\s*%s=(.*)$" % (opt,), content)
        if match:
            r = match.group(1).strip('"')
            if r != "":
                return r
        return default

    XKBLAYOUT = optval("XKBLAYOUT", "us")
    XKBVARIANT = optval("XKBVARIANT", "")
    XKBOPTIONS = optval("XKBOPTIONS", "")
    toggle = None
    for option in XKBOPTIONS.split(","):
        if option.startswith("grp:"):
            toggle = option[4:]
    return KeyboardSetting(layout=XKBLAYOUT, variant=XKBVARIANT, toggle=toggle)


class KeyboardModel:
    def __init__(self, root):
        self.config_path = os.path.join(root, "etc", "default", "keyboard")
        self.layout_for_lang = self.load_layout_suggestions()
        if os.path.exists(self.config_path):
            self.default_setting = from_config_file(self.config_path)
        else:
            self.default_setting = self.layout_for_lang["en_US.UTF-8"]
        self.keyboard_list = KeyboardList()
        self.keyboard_list.load_language("C")
        self._setting = None

    @property
    def setting(self):
        if self._setting is None:
            return self.default_setting
        return self._setting

    @setting.setter
    def setting(self, value):
        self.validate_setting(value)
        self._setting = value

    def validate_setting(self, setting: KeyboardSetting) -> None:
        layout_tokens = setting.layout.split(",")
        variant_tokens = setting.variant.split(",")

        if len(layout_tokens) != len(variant_tokens):
            raise InconsistentMultiLayoutError(
                layouts=setting.layout, variants=setting.variant
            )

        for layout, variant in zip(layout_tokens, variant_tokens):
            kbd_layout = self.keyboard_list.layout_map.get(layout)
            if kbd_layout is None:
                raise ValueError(f'Unknown keyboard layout "{layout}"')
            if not any(
                kbd_variant.code == variant for kbd_variant in kbd_layout.variants
            ):
                raise ValueError(
                    f'Unknown keyboard variant "{variant}" for layout "{layout}"'
                )

    def render_config_file(self):
        options = ""
        if self.setting.toggle:
            options = "grp:" + self.setting.toggle
        return etc_default_keyboard_template.format(
            layout=self.setting.layout, variant=self.setting.variant, options=options
        )

    def render(self):
        return {
            "write_files": {
                "etc_default_keyboard": {
                    "path": "etc/default/keyboard",
                    "content": self.render_config_file(),
                    "permissions": 0o644,
                },
            },
            "curthooks_commands": {
                # The below command must be run after updating
                # etc/default/keyboard on the target so that the initramfs uses
                # the keyboard mapping selected by the user.  See LP #1894009
                "002-setupcon-save-only": [
                    "curtin",
                    "in-target",
                    "--",
                    "setupcon",
                    "--save-only",
                ],
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
            path = resource_path("kbds") + "/keyboard-configuration.yaml"

        with open(path) as fp:
            data = yaml.safe_load(fp)

        ret = {}
        for k, v in data.items():
            ret[k] = KeyboardSetting(**v)
        return ret


class KeyboardList:
    def __init__(self):
        self._kbnames_dir = resource_path("kbds")
        self.serializer = Serializer(compact=True)
        self._clear()

    def _file_for_lang(self, code):
        return os.path.join(self._kbnames_dir, code + ".jsonl")

    def _has_language(self, code):
        return os.path.exists(self._file_for_lang(code))

    def load_language(self, code):
        if "." in code:
            code = code.split(".")[0]
        if not self._has_language(code):
            code = code.split("_")[0]
        if not self._has_language(code):
            code = "C"

        if code == self.current_lang:
            return

        self._clear()

        with open(self._file_for_lang(code)) as kbdnames:
            self.layouts = []
            self.layout_map = {}
            for line in kbdnames:
                kbd_layout = self.serializer.from_json(KeyboardLayout, line)
                self.layouts.append(kbd_layout)
                self.layout_map[kbd_layout.code] = kbd_layout
        self.current_lang = code

    def _clear(self):
        self.current_lang = None
        self.layouts = []
        self.layout_map = {}
