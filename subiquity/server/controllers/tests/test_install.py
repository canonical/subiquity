# Copyright 2022 Canonical, Ltd.
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

from pathlib import Path
import subprocess
import unittest
from unittest.mock import ANY, Mock, mock_open, patch

from subiquity.server.controllers.install import (
    InstallController,
    )

from subiquitycore.tests.mocks import make_app


class TestWriteConfig(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.controller = InstallController(make_app())
        self.controller.write_config = unittest.mock.Mock()
        self.controller.app.note_file_for_apport = Mock()
        self.controller.app.report_start_event = Mock()
        self.controller.app.report_finish_event = Mock()

        self.controller.model.target = "/target"

    @patch("subiquity.server.controllers.install.run_curtin_command")
    async def test_run_curtin_install_step(self, run_cmd):

        with patch("subiquity.server.controllers.install.open",
                   mock_open()) as m_open:
            await self.controller.run_curtin_step(
                name='MyStep',
                stages=["partitioning", "extract"],
                config_file=Path("/config.yaml"),
                source="/source",
                config=self.controller.base_config(
                    logs_dir=Path("/"), resume_data_file=Path("resume-data"))
                )

        m_open.assert_called_once_with("/curtin-install.log", mode="a")

        run_cmd.assert_called_once_with(
                self.controller.app,
                ANY,
                "install", "/source",
                "--set", 'json:stages=["partitioning", "extract"]',
                config="/config.yaml",
                private_mounts=False)

    def test_base_config(self):

        config = self.controller.base_config(
            logs_dir=Path("/logs"), resume_data_file=Path("resume-data"))

        self.assertDictEqual(config, {
            "install": {
                "target": "/target",
                "unmount": "disabled",
                "save_install_config": False,
                "save_install_log": False,
                "log_file": "/logs/curtin-install.log",
                "log_file_append": True,
                "error_tarfile": "/logs/curtin-errors.tar",
                "resume_data": "resume-data",
                }
            })

    def test_generic_config(self):
        with patch.object(self.controller.model, "render",
                          return_value={"key": "value"}):
            config = self.controller.generic_config(key2="value2")

        self.assertEqual(
            config,
            {
                "key": "value",
                "key2": "value2",
            })


class TestInstallController(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.controller = InstallController(make_app())
        self.controller.app.report_start_event = Mock()
        self.controller.app.report_finish_event = Mock()
        self.controller.model.target = "/target"

    @patch("asyncio.sleep")
    async def test_install_package(self, m_sleep):
        run_curtin = "subiquity.server.controllers.install.run_curtin_command"
        error = subprocess.CalledProcessError(
                returncode=1, cmd="curtin system-install git")

        with patch(run_curtin):
            await self.controller.install_package(package="git")
            m_sleep.assert_not_called()

        m_sleep.reset_mock()
        with patch(run_curtin, side_effect=(error, None, None)):
            await self.controller.install_package(package="git")
            m_sleep.assert_called_once()

        m_sleep.reset_mock()
        with patch(run_curtin, side_effect=(error, error, error, error)):
            with self.assertRaises(subprocess.CalledProcessError):
                await self.controller.install_package(package="git")
