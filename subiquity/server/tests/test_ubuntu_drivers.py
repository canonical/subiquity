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

from subprocess import CalledProcessError
import unittest
from unittest.mock import patch, AsyncMock, Mock

from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.util import run_coro

from subiquity.server.ubuntu_drivers import (
    UbuntuDriversInterface,
    UbuntuDriversClientInterface,
    CommandNotFoundError,
    )


class TestUbuntuDriversInterface(unittest.TestCase):
    def setUp(self):
        self.app = make_app()

    @patch.multiple(UbuntuDriversInterface, __abstractmethods__=set())
    def test_init(self):
        ubuntu_drivers = UbuntuDriversInterface(self.app, gpgpu=False)

        self.assertEqual(ubuntu_drivers.app, self.app)
        self.assertEqual(ubuntu_drivers.list_drivers_cmd, [
            "ubuntu-drivers", "list",
            "--recommended",
            ])
        self.assertEqual(ubuntu_drivers.install_drivers_cmd, [
            "ubuntu-drivers", "install"])

        ubuntu_drivers = UbuntuDriversInterface(self.app, gpgpu=True)
        self.assertEqual(ubuntu_drivers.list_drivers_cmd, [
            "ubuntu-drivers", "list",
            "--recommended", "--gpgpu",
            ])
        self.assertEqual(ubuntu_drivers.install_drivers_cmd, [
            "ubuntu-drivers", "install", "--gpgpu"])

    @patch.multiple(UbuntuDriversInterface, __abstractmethods__=set())
    @patch("subiquity.server.ubuntu_drivers.run_curtin_command")
    def test_install_drivers(self, mock_run_curtin_command):
        ubuntu_drivers = UbuntuDriversInterface(self.app, gpgpu=False)
        run_coro(ubuntu_drivers.install_drivers(
            root_dir="/target",
            context="installing third-party drivers"))
        mock_run_curtin_command.assert_called_once_with(
                self.app, "installing third-party drivers",
                "in-target", "-t", "/target",
                "--",
                "ubuntu-drivers", "install"
                )

    @patch.multiple(UbuntuDriversInterface, __abstractmethods__=set())
    def test_drivers_from_output(self):
        ubuntu_drivers = UbuntuDriversInterface(self.app, gpgpu=False)

        output = """\
nvidia-driver-470 linux-modules-nvidia-470-generic-hwe-20.04
"""
        self.assertEqual(
                ubuntu_drivers._drivers_from_output(output=output),
                ["nvidia-driver-470"])

        # Make sure empty lines are discarded
        output = """
nvidia-driver-470 linux-modules-nvidia-470-generic-hwe-20.04

nvidia-driver-510 linux-modules-nvidia-510-generic-hwe-20.04

"""

        self.assertEqual(
                ubuntu_drivers._drivers_from_output(output=output),
                ["nvidia-driver-470", "nvidia-driver-510"])


class TestUbuntuDriversClientInterface(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.ubuntu_drivers = UbuntuDriversClientInterface(
                self.app, gpgpu=False)

    def test_ensure_cmd_exists(self):
        with patch.object(
                self.app, "command_runner",
                create=True, new_callable=AsyncMock) as mock_runner:
            # On success
            run_coro(self.ubuntu_drivers.ensure_cmd_exists("/target"))
            mock_runner.run.assert_called_once_with(
                    [
                        "chroot", "/target",
                        "sh", "-c", "command -v ubuntu-drivers",
                    ])

            # On process failure
            mock_runner.run.side_effect = CalledProcessError(
                    returncode=1,
                    cmd=["sh", "-c", "command -v ubuntu-drivers"])

            with self.assertRaises(CommandNotFoundError):
                run_coro(self.ubuntu_drivers.ensure_cmd_exists("/target"))

    @patch("subiquity.server.ubuntu_drivers.run_curtin_command")
    def test_list_drivers(self, mock_run_curtin_command):
        # Make sure this gets decoded as utf-8.
        mock_run_curtin_command.return_value = Mock(stdout=b"""\
nvidia-driver-510 linux-modules-nvidia-510-generic-hwe-20.04
""")
        drivers = run_coro(self.ubuntu_drivers.list_drivers(
            root_dir="/target",
            context="listing third-party drivers"))

        mock_run_curtin_command.assert_called_once_with(
                self.app, "listing third-party drivers",
                "in-target", "-t", "/target",
                "--",
                "ubuntu-drivers", "list", "--recommended",
                capture=True)

        self.assertEqual(drivers, ["nvidia-driver-510"])
