# Copyright 2025 Canonical, Ltd.
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
import unittest.mock

from subiquity.server import shutdown


@unittest.mock.patch("subiquity.server.shutdown.arun_command")
class TestInitiateShutdown(unittest.IsolatedAsyncioTestCase):
    async def test_reboot_success(self, arun_command):
        await shutdown.initiate_reboot()
        arun_command.assert_called_once_with(
            ["systemctl", "reboot", "--ignore-inhibitors"]
        )

    async def test_reboot_failure(self, arun_command):
        arun_command.side_effect = subprocess.CalledProcessError(
            cmd=["systemctl", "..."], returncode=1, stderr="Permission Denied"
        )

        with self.assertRaises(subprocess.CalledProcessError):
            await shutdown.initiate_reboot()

        arun_command.assert_called_once_with(
            ["systemctl", "reboot", "--ignore-inhibitors"]
        )

    async def test_reboot_to_fw_success(self, arun_command):
        await shutdown.initiate_reboot_to_fw_settings()
        arun_command.assert_called_once_with(
            ["systemctl", "reboot", "--firmware-setup", "--ignore-inhibitors"]
        )

    async def test_reboot_to_fw_failure(self, arun_command):
        arun_command.side_effect = subprocess.CalledProcessError(
            cmd=["systemctl", "..."],
            returncode=1,
            stderr="Cannot indicate to EFI to boot into setup mode:"
            " Firmware does not support boot into firmware.",
        )

        with self.assertRaises(subprocess.CalledProcessError):
            await shutdown.initiate_reboot_to_fw_settings()

        arun_command.assert_called_once_with(
            ["systemctl", "reboot", "--firmware-setup", "--ignore-inhibitors"]
        )

    async def test_poweroff_success(self, arun_command):
        await shutdown.initiate_poweroff()
        arun_command.assert_called_once_with(
            ["systemctl", "poweroff", "--ignore-inhibitors"]
        )

    async def test_poweroff_failure(self, arun_command):
        arun_command.side_effect = subprocess.CalledProcessError(
            cmd=["systemctl", "..."], returncode=1, stderr="Permission Denied"
        )

        with self.assertRaises(subprocess.CalledProcessError):
            await shutdown.initiate_poweroff()

        arun_command.assert_called_once_with(
            ["systemctl", "poweroff", "--ignore-inhibitors"]
        )
