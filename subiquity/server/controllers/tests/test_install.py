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
import unittest
from unittest.mock import ANY, Mock, mock_open, patch

from subiquity.server.controllers.install import (
    InstallController,
    CurtinInstallStep,
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
        step = CurtinInstallStep(
                name="MyStep",
                stages=["partitioning", "extract"],
                config_file=Path("/config.yaml"),
                log_file=Path("/logfile.log"),
                error_file=Path("/error.tar"),
                acquire_config=self.controller.acquire_initial_config)

        with patch("subiquity.server.controllers.install.open",
                   mock_open()) as m_open:
            await self.controller.run_curtin_install_step(
                    step=step,
                    resume_data_file=Path("/resume-data.json"),
                    source="/source")

        m_open.assert_called_once_with("/logfile.log", mode="a")

        run_cmd.assert_called_once_with(
                self.controller.app,
                ANY,
                "install", "/source",
                "--set", 'json:stages=["partitioning", "extract"]',
                config="/config.yaml",
                private_mounts=False)

    def test_acquire_initial_config(self):
        step = CurtinInstallStep(
                name="initial",
                stages=["initial"],
                config_file=Path("/config-initial.yaml"),
                log_file=Path("/logfile-initial.log"),
                error_file=Path("/error-initial.tar"),
                acquire_config=self.controller.acquire_initial_config)

        config = self.controller.acquire_initial_config(
                step=step, resume_data_file=Path("/resume-data.json"))

        self.assertDictEqual(config, {
            "install": {
                "target": "/target",
                "unmount": "disabled",
                "save_install_config": False,
                "save_install_log": False,
                "log_file": "/logfile-initial.log",
                "log_file_append": True,
                "error_tarfile": "/error-initial.tar",
                "resume_data": "/resume-data.json",
                }
            })

    def test_acquire_generic_config(self):
        step = CurtinInstallStep(
                name="partitioning",
                stages=["partitioning"],
                config_file=Path("/config-partitioning.yaml"),
                log_file=Path("/logfile-partitioning.log"),
                error_file=Path("/error-partitioning.tar"),
                acquire_config=self.controller.acquire_initial_config)

        with patch.object(self.controller.model, "render",
                          return_value={"install": {}}):
            config = self.controller.acquire_generic_config(
                    step=step, resume_data_file=Path("/resume-data.json"))

        self.assertEqual(config["install"]["log_file"],
                         "/logfile-partitioning.log")
        self.assertIs(config["install"]["log_file_append"], True)
        self.assertEqual(config["install"]["error_tarfile"],
                         "/error-partitioning.tar")
        self.assertEqual(config["install"]["resume_data"],
                         "/resume-data.json")
