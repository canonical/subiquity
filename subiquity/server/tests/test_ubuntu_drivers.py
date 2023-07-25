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

import unittest
from subprocess import CalledProcessError
from unittest.mock import AsyncMock, Mock, patch

from subiquity.server.dryrun import DRConfig
from subiquity.server.ubuntu_drivers import (
    CommandNotFoundError,
    UbuntuDriversClientInterface,
    UbuntuDriversInterface,
    UbuntuDriversRunDriversInterface,
)
from subiquitycore.tests.mocks import make_app


class TestUbuntuDriversInterface(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()

    @patch.multiple(UbuntuDriversInterface, __abstractmethods__=set())
    def test_init(self):
        ubuntu_drivers = UbuntuDriversInterface(self.app, gpgpu=False)

        self.assertEqual(ubuntu_drivers.app, self.app)
        self.assertEqual(
            ubuntu_drivers.list_drivers_cmd,
            [
                "ubuntu-drivers",
                "list",
                "--recommended",
            ],
        )
        self.assertEqual(
            ubuntu_drivers.install_drivers_cmd,
            ["ubuntu-drivers", "install", "--no-oem"],
        )

        ubuntu_drivers = UbuntuDriversInterface(self.app, gpgpu=True)
        self.assertEqual(
            ubuntu_drivers.list_drivers_cmd,
            [
                "ubuntu-drivers",
                "list",
                "--recommended",
                "--gpgpu",
            ],
        )
        self.assertEqual(
            ubuntu_drivers.install_drivers_cmd,
            ["ubuntu-drivers", "install", "--no-oem", "--gpgpu"],
        )

    @patch.multiple(UbuntuDriversInterface, __abstractmethods__=set())
    @patch("subiquity.server.ubuntu_drivers.run_curtin_command")
    async def test_install_drivers(self, mock_run_curtin_command):
        ubuntu_drivers = UbuntuDriversInterface(self.app, gpgpu=False)
        await ubuntu_drivers.install_drivers(
            root_dir="/target", context="installing third-party drivers"
        )
        mock_run_curtin_command.assert_called_once_with(
            self.app,
            "installing third-party drivers",
            "in-target",
            "-t",
            "/target",
            "--",
            "ubuntu-drivers",
            "install",
            "--no-oem",
            private_mounts=True,
        )

    @patch.multiple(UbuntuDriversInterface, __abstractmethods__=set())
    def test_drivers_from_output(self):
        ubuntu_drivers = UbuntuDriversInterface(self.app, gpgpu=False)

        output = """\
nvidia-driver-470 linux-modules-nvidia-470-generic-hwe-20.04
"""
        self.assertEqual(
            ubuntu_drivers._drivers_from_output(output=output), ["nvidia-driver-470"]
        )

        # Make sure empty lines are discarded
        output = """
nvidia-driver-470 linux-modules-nvidia-470-generic-hwe-20.04

nvidia-driver-510 linux-modules-nvidia-510-generic-hwe-20.04

"""

        self.assertEqual(
            ubuntu_drivers._drivers_from_output(output=output),
            ["nvidia-driver-470", "nvidia-driver-510"],
        )


class TestUbuntuDriversClientInterface(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()
        self.ubuntu_drivers = UbuntuDriversClientInterface(self.app, gpgpu=False)

    async def test_ensure_cmd_exists(self):
        with patch.object(
            self.app, "command_runner", create=True, new_callable=AsyncMock
        ) as mock_runner:
            # On success
            await self.ubuntu_drivers.ensure_cmd_exists("/target")
            mock_runner.run.assert_called_once_with(
                [
                    "chroot",
                    "/target",
                    "sh",
                    "-c",
                    "command -v ubuntu-drivers",
                ]
            )

            # On process failure
            mock_runner.run.side_effect = CalledProcessError(
                returncode=1, cmd=["sh", "-c", "command -v ubuntu-drivers"]
            )

            with self.assertRaises(CommandNotFoundError):
                await self.ubuntu_drivers.ensure_cmd_exists("/target")

    @patch("subiquity.server.ubuntu_drivers.run_curtin_command")
    async def test_list_drivers(self, mock_run_curtin_command):
        # Make sure this gets decoded as utf-8.
        mock_run_curtin_command.return_value = Mock(
            stdout=b"""\
nvidia-driver-510 linux-modules-nvidia-510-generic-hwe-20.04
"""
        )
        drivers = await self.ubuntu_drivers.list_drivers(
            root_dir="/target", context="listing third-party drivers"
        )

        mock_run_curtin_command.assert_called_once_with(
            self.app,
            "listing third-party drivers",
            "in-target",
            "-t",
            "/target",
            "--",
            "ubuntu-drivers",
            "list",
            "--recommended",
            capture=True,
            private_mounts=True,
        )

        self.assertEqual(drivers, ["nvidia-driver-510"])

    @patch("subiquity.server.ubuntu_drivers.run_curtin_command")
    async def test_list_oem(self, mock_run_curtin_command):
        # Make sure this gets decoded as utf-8.
        mock_run_curtin_command.return_value = Mock(
            stdout=b"""\
oem-somerville-tentacool-meta
"""
        )
        drivers = await self.ubuntu_drivers.list_oem(
            root_dir="/target", context="listing OEM meta-packages"
        )

        mock_run_curtin_command.assert_called_once_with(
            self.app,
            "listing OEM meta-packages",
            "in-target",
            "-t",
            "/target",
            "--",
            "ubuntu-drivers",
            "list-oem",
            capture=True,
            private_mounts=True,
        )

        self.assertEqual(drivers, ["oem-somerville-tentacool-meta"])


class TestUbuntuDriversRunDriversInterface(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.dr_cfg = DRConfig()
        self.app.dr_cfg.ubuntu_drivers_run_on_host_umockdev = None
        self.ubuntu_drivers = UbuntuDriversRunDriversInterface(self.app, gpgpu=False)

    def test_init_no_umockdev(self):
        self.app.dr_cfg.ubuntu_drivers_run_on_host_umockdev = None
        ubuntu_drivers = UbuntuDriversRunDriversInterface(self.app, gpgpu=False)
        self.assertEqual(ubuntu_drivers.list_oem_cmd, ["ubuntu-drivers", "list-oem"])
        self.assertEqual(
            ubuntu_drivers.list_drivers_cmd[0:2], ["ubuntu-drivers", "list"]
        )
        self.assertEqual(
            ubuntu_drivers.install_drivers_cmd[0:2], ["ubuntu-drivers", "install"]
        )

    def test_init_with_umockdev(self):
        self.app.dr_cfg.ubuntu_drivers_run_on_host_umockdev = "/xps.yaml"
        ubuntu_drivers = UbuntuDriversRunDriversInterface(self.app, gpgpu=False)
        self.assertEqual(
            ubuntu_drivers.list_oem_cmd,
            [
                "scripts/umockdev-wrapper.py",
                "--config",
                "/xps.yaml",
                "--",
                "ubuntu-drivers",
                "list-oem",
            ],
        )
        self.assertEqual(
            ubuntu_drivers.list_drivers_cmd[0:6],
            [
                "scripts/umockdev-wrapper.py",
                "--config",
                "/xps.yaml",
                "--",
                "ubuntu-drivers",
                "list",
            ],
        )
        self.assertEqual(
            ubuntu_drivers.install_drivers_cmd[0:6],
            [
                "scripts/umockdev-wrapper.py",
                "--config",
                "/xps.yaml",
                "--",
                "ubuntu-drivers",
                "install",
            ],
        )

    @patch("subiquity.server.ubuntu_drivers.arun_command")
    async def test_ensure_cmd_exists(self, mock_arun_command):
        await self.ubuntu_drivers.ensure_cmd_exists("/target")
        mock_arun_command.assert_called_once_with(
            ["sh", "-c", "command -v ubuntu-drivers"], check=True
        )
