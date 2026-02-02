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
import subprocess
from unittest.mock import ANY, Mock, patch

from subiquity.server.runner import (
    DryRunCommandRunner,
    LoggedCommandRunner,
    SleepAndEchoWrapper,
    SystemdRunWrapper,
    _dollar_escape,
)
from subiquitycore.tests import SubiTestCase


class TestDollarEscape(SubiTestCase):
    def test_no_dollar(self):
        self.assertEqual("No dollar sign", _dollar_escape("No dollar sign"))

    def test_encrypted_password(self):
        self.assertEqual("$$6$$xxx", _dollar_escape("$6$xxx"))

    def test_multiple_dollars(self):
        self.assertEqual("a$$$$$$b", _dollar_escape("a$$$b"))


class TestSystemdRunWrapper(SubiTestCase):
    def test_init(self):
        with patch("os.geteuid", return_value=0):
            wrapper = SystemdRunWrapper(ident="my-identifier")
            self.assertEqual(wrapper.ident, "my-identifier")
            self.assertIs(wrapper.use_systemd_user, False)

        with patch("os.geteuid", return_value=1000):
            wrapper = SystemdRunWrapper(ident="my-identifier")
            self.assertIs(wrapper.use_systemd_user, True)

        wrapper = SystemdRunWrapper(ident="my-identifier", use_systemd_user=True)
        self.assertIs(wrapper.use_systemd_user, True)

        wrapper = SystemdRunWrapper(ident="my-identifier", use_systemd_user=False)
        self.assertIs(wrapper.use_systemd_user, False)

    def test_wrap(self):
        wrapper = SystemdRunWrapper(ident="my-id", use_systemd_user=False)
        environ = {
            "PATH": "/snap/subiquity/x1/bin",
            "PYTHONPATH": "/usr/lib/python3.12/site-packages",
            "PYTHON": "/snap/subiquity/x1/usr/bin/python3.12",
            "TARGET_MOUNT_POINT": "/target",
            "SNAP": "/snap/subiquity/x1",
            "SAMPLE": "should-not-be-exported",
        }

        with patch.dict(os.environ, environ, clear=True):
            cmd = wrapper.wrap(
                ["/bin/ls", "/root"],
                private_mounts=True,
                capture=False,
                stdin=subprocess.DEVNULL,
            )

        expected = [
            "systemd-run",
            "--wait",
            "--same-dir",
            "--property",
            "SyslogIdentifier=my-id",
            "--property",
            "PrivateMounts=yes",
            "--setenv",
            "PATH=/snap/subiquity/x1/bin",
            "--setenv",
            "PYTHONPATH=/usr/lib/python3.12/site-packages",
            "--setenv",
            "PYTHON=/snap/subiquity/x1/usr/bin/python3.12",
            "--setenv",
            "TARGET_MOUNT_POINT=/target",
            "--setenv",
            "SNAP=/snap/subiquity/x1",
            "--",
            "/bin/ls",
            "/root",
        ]
        self.assertEqual(cmd, expected)

    def test_wrap__no_use_systemd_user(self):
        wrapper = SystemdRunWrapper(ident="my-id", use_systemd_user=True)
        # Make sure unset variables are ignored
        environ = {
            "PYTHONPATH": "/usr/lib/python3.12/site-packages",
        }
        with patch.dict(os.environ, environ, clear=True):
            cmd = wrapper.wrap(
                ["/bin/ls", "/root"],
                private_mounts=False,
                capture=True,
                stdin=subprocess.DEVNULL,
            )

        expected = [
            "systemd-run",
            "--wait",
            "--same-dir",
            "--property",
            "SyslogIdentifier=my-id",
            "--user",
            "--pipe",
            "--setenv",
            "PYTHONPATH=/usr/lib/python3.12/site-packages",
            "--",
            "/bin/ls",
            "/root",
        ]
        self.assertEqual(cmd, expected)

    def test_wrap__with_escapes(self):
        wrapper = SystemdRunWrapper(ident="my-id", use_systemd_user=True)
        # Make sure $ signs are escaped.
        with patch.dict(os.environ, {}, clear=True):
            cmd = wrapper.wrap(
                ["/usr/bin/echo", "$6$123456"],
                private_mounts=False,
                capture=True,
                stdin=subprocess.DEVNULL,
            )

        expected = [
            "systemd-run",
            "--wait",
            "--same-dir",
            "--property",
            "SyslogIdentifier=my-id",
            "--user",
            "--pipe",
            "--",
            "/usr/bin/echo",
            "$$6$$123456",
        ]
        self.assertEqual(cmd, expected)

    def test_wrap__pipe_stdin_but_no_capture(self):
        wrapper = SystemdRunWrapper(ident="my-id", use_systemd_user=True)
        with self.assertRaisesRegex(ValueError, r"cannot pipe stdin but not stdout"):
            wrapper.wrap(
                ["cat", "/etc/shells"],
                private_mounts=False,
                capture=False,
                stdin=subprocess.PIPE,
            )


class TestSleepAndEchoWrapper(SubiTestCase):
    def test_get_delay_for_cmd(self):
        wrapper = SleepAndEchoWrapper(delay_multiplier=10)
        # Most commands use the default delay
        delay = wrapper._get_delay_for_cmd(["/bin/ls", "/root"])
        self.assertEqual(10, delay)

        # Commands containing "unattended-upgrades" use delay * 3
        delay = wrapper._get_delay_for_cmd(
            [
                "python3",
                "-m",
                "curtin",
                "in-target",
                "-t",
                "/target",
                "--",
                "unattended-upgrades",
                "-v",
            ]
        )
        self.assertEqual(delay, 30)

        # Commands having scripts/replay will actually be executed - no delay.
        delay = wrapper._get_delay_for_cmd(["scripts/replay-curtin-log.py"])
        self.assertEqual(delay, 0)

        # chzdev commands multiply a random number with 0.4 * default_delay
        with patch("random.random", return_value=1) as m_random:
            delay = wrapper._get_delay_for_cmd(["chzdev", "--enable", "0.0.1507"])
        self.assertEqual(delay, 1 * 0.4 * 10)
        m_random.assert_called_once()

    def test_wrap__default(self):
        wrapper = SleepAndEchoWrapper(delay_multiplier=10)
        expected = [
            "scripts/sleep-then-execute.sh",
            "10",
            "echo",
            "not running:",
            "/bin/cat",
            "-e",
        ]
        self.assertEqual(expected, wrapper.wrap(["/bin/cat", "-e"]))

    def test_wrap__replay_curtin(self):
        wrapper = SleepAndEchoWrapper(delay_multiplier=10)
        self.assertEqual(
            ["scripts/replay-curtin-log.py"],
            wrapper.wrap(["scripts/replay-curtin-log.py"]),
        )


class TestLoggedCommandRunner(SubiTestCase):
    def test_init(self):
        with patch(
            "subiquity.server.runner.SystemdRunWrapper",
            return_value=None,
            autospec=True,
        ) as m_wrapper_init:
            LoggedCommandRunner(ident="my-identifier")
        m_wrapper_init.assert_called_once_with(
            ident="my-identifier", use_systemd_user=None
        )

        with patch(
            "subiquity.server.runner.SystemdRunWrapper",
            return_value=None,
            autospec=True,
        ) as m_wrapper_init:
            LoggedCommandRunner(ident="my-identifier", use_systemd_user=True)
        m_wrapper_init.assert_called_once_with(
            ident="my-identifier", use_systemd_user=True
        )

        with patch(
            "subiquity.server.runner.SystemdRunWrapper",
            return_value=None,
            autospec=True,
        ) as m_wrapper_init:
            LoggedCommandRunner(ident="my-identifier", use_systemd_user=False)
        m_wrapper_init.assert_called_once_with(
            ident="my-identifier", use_systemd_user=False
        )

    def test_wrap_command(self):
        runner = LoggedCommandRunner(ident="my-identifier")

        with patch.object(runner.systemd_run_wrapper, "wrap", autospec=True) as m_wrap:
            runner.wrap_command(
                ["dpkg", "-i", "wpa-supplicant"],
                private_mounts=False,
                capture=True,
                stdin=subprocess.DEVNULL,
            )

        m_wrap.assert_called_once_with(
            ["dpkg", "-i", "wpa-supplicant"],
            private_mounts=False,
            capture=True,
            stdin=subprocess.DEVNULL,
        )

    async def test_start__no_input(self):
        runner = LoggedCommandRunner(ident="my-id", use_systemd_user=False)

        with patch("subiquity.server.runner.astart_command") as astart_mock:
            await runner.start(["/bin/ls"], stdout=subprocess.PIPE)

        expected_cmd = ANY
        astart_mock.assert_called_once_with(
            expected_cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE
        )

    async def test_start__pipe_stdin_and_capture(self):
        runner = LoggedCommandRunner(ident="my-id", use_systemd_user=False)

        with patch("subiquity.server.runner.astart_command") as astart_mock:
            await runner.start(["/bin/cat"], stdin=subprocess.PIPE, capture=True)

        expected_cmd = ANY
        astart_mock.assert_called_once_with(expected_cmd, stdin=subprocess.PIPE)

    async def test_run__no_input(self):
        runner = LoggedCommandRunner(ident="my-id", use_systemd_user=False)

        proc_mock = Mock()

        p_start = patch.object(runner, "start", return_value=proc_mock, autospec=True)
        p_wait = patch.object(runner, "wait")

        with p_start as m_start, p_wait as m_wait:
            await runner.run(["/bin/cat"])

        m_start.assert_called_once_with(["/bin/cat"], stdin=subprocess.DEVNULL)
        m_wait.assert_called_once_with(proc_mock, input=None)


class TestDryRunCommandRunner(SubiTestCase):
    def setUp(self):
        self.runner = DryRunCommandRunner(
            ident="my-identifier", delay=10, use_systemd_user=True
        )

    def test_init(self):
        self.assertEqual(self.runner.systemd_run_wrapper.ident, "my-identifier")
        self.assertEqual(self.runner.systemd_run_wrapper.use_systemd_user, True)
        self.assertEqual(self.runner.sleep_and_echo_wrapper.delay_multiplier, 10)

    @patch.object(
        LoggedCommandRunner,
        "wrap_command",
        wraps=LoggedCommandRunner.wrap_command,
        autospec=True,
    )
    def test_wrap_command(self, mock_super):
        rv = Mock()

        with patch.object(
            self.runner.sleep_and_echo_wrapper, "wrap", return_value=[rv]
        ) as m_wrap:
            self.runner.wrap_command(
                ["dpkg", "-i", "wpa-supplicant"],
                private_mounts=False,
                capture=True,
                stdin=subprocess.DEVNULL,
            )

        m_wrap.assert_called_once_with(["dpkg", "-i", "wpa-supplicant"])
        # We use patch(..., wraps=...), so expect arg1 to be "self" (i.e., the runner).
        mock_super.assert_called_once_with(
            self.runner,
            [rv],
            private_mounts=False,
            capture=True,
            stdin=subprocess.DEVNULL,
        )
