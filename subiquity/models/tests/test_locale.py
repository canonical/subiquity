# Copyright 2023 Canonical, Ltd.
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

import subprocess
import unittest
from unittest import mock

from subiquity.models.locale import LocaleModel


class TestLocaleModel(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.model = LocaleModel(chroot_prefix="/")

    def test_switch_language(self):
        self.model.switch_language("fr_FR.UTF-8")
        self.assertEqual(self.model.selected_language, "fr_FR.UTF-8")

    async def test_localectl_set_locale(self):
        expected_cmd = [
            "localectl",
            "set-locale",
            "fr_FR.UTF-8",
        ]
        self.model.selected_language = "fr_FR.UTF-8"
        with mock.patch("subiquity.models.locale.arun_command") as arun_cmd:
            await self.model.localectl_set_locale()
        arun_cmd.assert_called_once_with(expected_cmd, check=True)
        self.model.selected_language = "fr_FR"
        with mock.patch("subiquity.models.locale.arun_command") as arun_cmd:
            # Currently, the default for fr_FR is fr_FR.ISO8859-1
            with mock.patch(
                "subiquity.models.locale.locale.normalize", return_value="fr_FR.UTF-8"
            ):
                await self.model.localectl_set_locale()
        arun_cmd.assert_called_once_with(expected_cmd, check=True)

    async def test_try_localectl_set_locale(self):
        self.model.selected_language = "fr_FR.UTF-8"
        exc = subprocess.CalledProcessError(returncode=1, cmd=["localedef"])
        with mock.patch("subiquity.models.locale.arun_command", side_effect=exc):
            await self.model.try_localectl_set_locale()
        with mock.patch("subiquity.models.locale.arun_command"):
            await self.model.try_localectl_set_locale()
