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

import subprocess
import unittest
from pathlib import Path
from unittest.mock import ANY, AsyncMock, Mock, call, mock_open, patch

from curtin.util import EFIBootEntry, EFIBootState

from subiquity.common.types import PackageInstallState
from subiquity.models.tests.test_filesystem import make_model_and_partition
from subiquity.server.controllers.install import InstallController
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
        with patch("subiquity.server.controllers.install.open", mock_open()) as m_open:
            await self.controller.run_curtin_step(
                name="MyStep",
                stages=["partitioning", "extract"],
                config_file=Path("/config.yaml"),
                source="/source",
                config=self.controller.base_config(
                    logs_dir=Path("/"), resume_data_file=Path("resume-data")
                ),
            )

        m_open.assert_called_once_with("/curtin-install.log", mode="a")

        run_cmd.assert_called_once_with(
            self.controller.app,
            ANY,
            "install",
            "--set",
            'json:stages=["partitioning", "extract"]',
            "/source",
            config="/config.yaml",
            private_mounts=False,
        )

    @patch("subiquity.server.controllers.install.run_curtin_command")
    async def test_run_curtin_install_step_no_src(self, run_cmd):
        with patch("subiquity.server.controllers.install.open", mock_open()) as m_open:
            await self.controller.run_curtin_step(
                name="MyStep",
                stages=["partitioning", "extract"],
                config_file=Path("/config.yaml"),
                source=None,
                config=self.controller.base_config(
                    logs_dir=Path("/"), resume_data_file=Path("resume-data")
                ),
            )

        m_open.assert_called_once_with("/curtin-install.log", mode="a")

        run_cmd.assert_called_once_with(
            self.controller.app,
            ANY,
            "install",
            "--set",
            'json:stages=["partitioning", "extract"]',
            config="/config.yaml",
            private_mounts=False,
        )

    def test_base_config(self):
        config = self.controller.base_config(
            logs_dir=Path("/logs"), resume_data_file=Path("resume-data")
        )

        self.assertDictEqual(
            config,
            {
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
            },
        )

    def test_generic_config(self):
        with patch.object(
            self.controller.model, "render", return_value={"key": "value"}
        ):
            config = self.controller.generic_config(key2="value2")

        self.assertEqual(
            config,
            {
                "key": "value",
                "key2": "value2",
            },
        )


efi_state_no_rp = EFIBootState(
    current="0000",
    timeout="0 seconds",
    order=["0000", "0002"],
    entries={
        "0000": EFIBootEntry(
            name="ubuntu", path="HD(1,GPT,...)/File(\\EFI\\ubuntu\\shimx64.efi)"
        ),
        "0001": EFIBootEntry(
            name="Windows Boot Manager",
            path="HD(1,GPT,...,0x82000)/File(\\EFI\\bootmgfw.efi",
        ),
        "0002": EFIBootEntry(
            name="Linux-Firmware-Updater",
            path="HD(1,GPT,...,0x800,0x100000)/File(\\shimx64.efi)\\.fwupd",
        ),
    },
)

efi_state_with_rp = EFIBootState(
    current="0000",
    timeout="0 seconds",
    order=["0000", "0002", "0003"],
    entries={
        "0000": EFIBootEntry(
            name="ubuntu", path="HD(1,GPT,...)/File(\\EFI\\ubuntu\\shimx64.efi)"
        ),
        "0001": EFIBootEntry(
            name="Windows Boot Manager",
            path="HD(1,GPT,...,0x82000)/File(\\EFI\\bootmgfw.efi",
        ),
        "0002": EFIBootEntry(
            name="Linux-Firmware-Updater",
            path="HD(1,GPT,...,0x800,0x100000)/File(\\shimx64.efi)\\.fwupd",
        ),
        "0003": EFIBootEntry(
            name="Restore Ubuntu to factory state",
            path="HD(1,GPT,...,0x800,0x100000)/File(\\shimx64.efi)",
        ),
    },
)

efi_state_with_dup_rp = EFIBootState(
    current="0000",
    timeout="0 seconds",
    order=["0000", "0002", "0004"],
    entries={
        "0000": EFIBootEntry(
            name="ubuntu", path="HD(1,GPT,...)/File(\\EFI\\ubuntu\\shimx64.efi)"
        ),
        "0001": EFIBootEntry(
            name="Windows Boot Manager",
            path="HD(1,GPT,...,0x82000)/File(\\EFI\\bootmgfw.efi",
        ),
        "0002": EFIBootEntry(
            name="Linux-Firmware-Updater",
            path="HD(1,GPT,...,0x800,0x100000)/File(\\shimx64.efi)\\.fwupd",
        ),
        "0003": EFIBootEntry(
            name="Restore Ubuntu to factory state",
            path="HD(1,GPT,...,0x800,0x100000)/File(\\shimx64.efi)",
        ),
        "0004": EFIBootEntry(
            name="Restore Ubuntu to factory state",
            path="HD(1,GPT,...,0x800,0x100000)/File(\\shimx64.efi)",
        ),
    },
)


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
            returncode=1, cmd="curtin system-install git"
        )

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

    def setup_rp_test(self):
        app = self.controller.app
        app.opts.dry_run = False
        fsc = app.controllers.Filesystem
        fsc.reset_partition_only = True
        app.package_installer = Mock()
        app.command_runner = Mock()
        self.run = app.command_runner.run = AsyncMock()
        app.package_installer.install_pkg = AsyncMock()
        app.package_installer.install_pkg.return_value = PackageInstallState.DONE
        fsm, self.part = make_model_and_partition()

    @patch("subiquity.server.controllers.install.get_efibootmgr")
    async def test_create_rp_boot_entry_add(self, m_get_efibootmgr):
        m_get_efibootmgr.side_effect = iter([efi_state_no_rp, efi_state_with_rp])
        self.setup_rp_test()
        await self.controller.create_rp_boot_entry(rp=self.part)
        calls = [
            call(
                [
                    "efibootmgr",
                    "--create",
                    "--loader",
                    "\\EFI\\boot\\shimx64.efi",
                    "--disk",
                    self.part.device.path,
                    "--part",
                    str(self.part.number),
                    "--label",
                    "Restore Ubuntu to factory state",
                ]
            ),
            call(
                [
                    "efibootmgr",
                    "--bootorder",
                    "0000,0002",
                ]
            ),
        ]
        self.run.assert_has_awaits(calls)

    @patch("subiquity.server.controllers.install.get_efibootmgr")
    async def test_create_rp_boot_entry_dup(self, m_get_efibootmgr):
        m_get_efibootmgr.side_effect = iter([efi_state_with_rp, efi_state_with_dup_rp])
        self.setup_rp_test()
        await self.controller.create_rp_boot_entry(rp=self.part)
        calls = [
            call(
                [
                    "efibootmgr",
                    "--create",
                    "--loader",
                    "\\EFI\\boot\\shimx64.efi",
                    "--disk",
                    self.part.device.path,
                    "--part",
                    str(self.part.number),
                    "--label",
                    "Restore Ubuntu to factory state",
                ]
            ),
            call(
                [
                    "efibootmgr",
                    "--delete-bootnum",
                    "--bootnum",
                    "0004",
                ]
            ),
        ]
        self.run.assert_has_awaits(calls)
