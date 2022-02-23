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

import os
from unittest.mock import patch

from subiquitycore.tests import SubiTestCase
from subiquity.server.runner import (
    LoggedCommandRunner,
    DryRunCommandRunner,
    )


class TestLoggedCommandRunner(SubiTestCase):
    def test_init(self):
        with patch("os.geteuid", return_value=0):
            runner = LoggedCommandRunner(ident="my-identifier")
            self.assertEqual(runner.ident, "my-identifier")
            self.assertEqual(runner.use_systemd_user, False)

        with patch("os.geteuid", return_value=1000):
            runner = LoggedCommandRunner(ident="my-identifier")
            self.assertEqual(runner.use_systemd_user, True)

        runner = LoggedCommandRunner(ident="my-identifier",
                                     use_systemd_user=True)
        self.assertEqual(runner.use_systemd_user, True)

        runner = LoggedCommandRunner(ident="my-identifier",
                                     use_systemd_user=False)
        self.assertEqual(runner.use_systemd_user, False)

    def test_forge_systemd_cmd(self):
        runner = LoggedCommandRunner(ident="my-id", use_systemd_user=False)
        environ = {
            "PATH": "/snap/subiquity/x1/bin",
            "PYTHONPATH": "/usr/lib/python3.8/site-packages",
            "PYTHON": "/snap/subiquity/x1/usr/bin/python3.8",
            "TARGET_MOUNT_POINT": "/target",
            "SNAP": "/snap/subiquity/x1",
            "DUMMY": "should-not-be-exported",
        }

        with patch.dict(os.environ, environ):
            cmd = runner._forge_systemd_cmd(
                    ["/bin/ls", "/root"],
                    private_mounts=True)

        expected = [
            "systemd-run",
            "--wait", "--same-dir",
            "--property", "SyslogIdentifier=my-id",
            "--property", "PrivateMounts=yes",
            "--setenv", "PATH=/snap/subiquity/x1/bin",
            "--setenv", "PYTHONPATH=/usr/lib/python3.8/site-packages",
            "--setenv", "PYTHON=/snap/subiquity/x1/usr/bin/python3.8",
            "--setenv", "TARGET_MOUNT_POINT=/target",
            "--setenv", "SNAP=/snap/subiquity/x1",
            "--",
            "/bin/ls", "/root",
        ]
        self.assertEqual(cmd, expected)

        runner = LoggedCommandRunner(ident="my-id", use_systemd_user=True)
        # Make sure unset variables are ignored
        environ = {
            "PYTHONPATH": "/usr/lib/python3.8/site-packages",
        }
        with patch.dict(os.environ, environ, clear=True):
            cmd = runner._forge_systemd_cmd(
                    ["/bin/ls", "/root"],
                    private_mounts=False)

        expected = [
            "systemd-run",
            "--wait", "--same-dir",
            "--property", "SyslogIdentifier=my-id",
            "--user",
            "--setenv", "PYTHONPATH=/usr/lib/python3.8/site-packages",
            "--",
            "/bin/ls", "/root",
        ]
        self.assertEqual(cmd, expected)


class TestDryRunCommandRunner(SubiTestCase):
    def setUp(self):
        self.runner = DryRunCommandRunner(ident="my-identifier",
                                          delay=10, use_systemd_user=True)

    def test_init(self):
        self.assertEqual(self.runner.ident, "my-identifier")
        self.assertEqual(self.runner.delay, 10)
        self.assertEqual(self.runner.use_systemd_user, True)

    @patch.object(LoggedCommandRunner, "_forge_systemd_cmd")
    def test_forge_systemd_cmd(self, mock_super):
        self.runner._forge_systemd_cmd(
                ["/bin/ls", "/root"],
                private_mounts=True)
        mock_super.assert_called_once_with(
                ["echo", "not running:", "/bin/ls", "/root"],
                private_mounts=True)

        mock_super.reset_mock()
        # Make sure exceptions are handled.
        self.runner._forge_systemd_cmd(["scripts/replay-curtin-log.py"],
                                       private_mounts=True)
        mock_super.assert_called_once_with(
                ["scripts/replay-curtin-log.py"],
                private_mounts=True)

    def test_get_delay_for_cmd(self):
        # Most commands use the default delay
        delay = self.runner._get_delay_for_cmd(["/bin/ls", "/root"])
        self.assertEqual(delay, 10)

        # Commands containing "unattended-upgrades" use delay * 3
        delay = self.runner._get_delay_for_cmd([
            "python3", "-m", "curtin",
            "in-target",
            "-t", "/target",
            "--",
            "unattended-upgrades", "-v",
        ])
        self.assertEqual(delay, 30)

        # Commands having scripts/replay will actually be executed - no delay.
        delay = self.runner._get_delay_for_cmd(
                ["scripts/replay-curtin-log.py"])
        self.assertEqual(delay, 0)
