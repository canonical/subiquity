# Copyright 2019 Canonical, Ltd.
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
import unittest
from unittest.mock import Mock, call, patch

import jsonschema
from jsonschema.validators import validator_for

from subiquity.common.types import KeyboardSetting
from subiquity.models.keyboard import KeyboardModel
from subiquity.server.controllers.keyboard import KeyboardController
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized


class opts:
    dry_run = True


class TestKeyboardController(SubiTestCase):
    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            KeyboardController.autoinstall_schema
        )
        JsonValidator.check_schema(KeyboardController.autoinstall_schema)


class TestSubiquityModel(SubiTestCase):
    async def test_write_config(self):
        os.environ["SUBIQUITY_REPLAY_TIMESCALE"] = "100"
        new_setting = KeyboardSetting("fr", "azerty")
        tmpdir = self.tmp_dir()
        model = KeyboardModel(tmpdir)
        model.setting = new_setting
        c = object.__new__(KeyboardController)
        c.opts = opts
        c.model = model
        await c.set_keyboard()
        read_setting = KeyboardModel(tmpdir).setting
        self.assertEqual(new_setting, read_setting)


class TestInputSource(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()
        self.controller = KeyboardController(self.app)

    @parameterized.expand(
        [
            ("us", "", "[('xkb','us')]", "us", ""),
            ("fr", "latin9", "[('xkb','fr+latin9')]", "fr", "latin9"),
            # non-latin layouts get expanded to a dual layout with a latin
            # fallback, same as for the "main" set_keyboard flow.
            ("ru", "", "[('xkb','ru')]", "us,ru", ","),
        ]
    )
    async def test_input_source(
        self,
        layout,
        variant,
        expected_xkb,
        expected_locale_layout,
        expected_locale_variant,
    ):
        with (
            patch(
                "subiquity.server.controllers.keyboard.arun_command"
            ) as mock_arun_command,
            patch("pwd.getpwnam") as mock_getpwnam,
        ):
            m = Mock()
            m.pw_uid = "99"
            mock_getpwnam.return_value = m
            self.app.opts.dry_run = False
            await self.controller.set_input_source(layout, variant, user="bar")
            gsettings = [
                "gsettings",
                "set",
                "org.gnome.desktop.input-sources",
                "sources",
                expected_xkb,
            ]
            gsettings_cmd = [
                "systemd-run",
                "--wait",
                "--uid=99",
                f'--setenv=DISPLAY={os.environ.get("DISPLAY", ":0")}',
                "--setenv=XDG_RUNTIME_DIR=/run/user/99",
                "--setenv=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/99/bus",
                "--",
                *gsettings,
            ]
            localectl_cmd = [
                "localectl",
                "--no-ask-password",
                "--no-convert",
                "--",
                "set-x11-keymap",
                expected_locale_layout,
                "",
                expected_locale_variant,
            ]
            self.assertEqual(
                mock_arun_command.call_args_list,
                [call(gsettings_cmd), call(localectl_cmd, check=True)],
            )
