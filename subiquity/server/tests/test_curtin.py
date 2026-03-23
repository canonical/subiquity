# Copyright 2026 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import unittest
from unittest import mock

from subiquity.server.curtin import (
    _CurtinCommand,
    _DryRunCurtinCommand,
    _FailingDryRunCurtinCommand,
    start_curtin_command,
)
from subiquity.server.runner import LoggedCommandRunner
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized


@mock.patch.object(_CurtinCommand, "__init__", wraps=_CurtinCommand.__init__)
@mock.patch.object(_CurtinCommand, "start", mock.AsyncMock())
class TestStartCurtinCommand(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.debug_flags = ()
        self.app.command_runner = mock.Mock(spec=LoggedCommandRunner)

    @parameterized.expand(
        (
            (False, (), _CurtinCommand),
            (True, (), _DryRunCurtinCommand),
            (True, ("install-fail"), _FailingDryRunCurtinCommand),
        ),
    )
    async def test_implementations(
        self, m_curtin_command_init, dry_run, debug_flags, expected_type
    ):
        self.app.opts.dry_run = dry_run
        self.app.debug_flags = debug_flags
        cmd = await start_curtin_command(
            self.app,
            mock.Mock(),
            "in-target",
            "--target",
            "/target",
            "--",
            "/bin/ls",
            private_mounts=False,
        )

        m_curtin_command_init.assert_called_once_with(
            self.app.opts,
            self.app.command_runner,
            "in-target",
            "--target",
            "/target",
            "--",
            "/bin/ls",
            config=None,
            runner_kwargs={},
        )
        self.assertEqual(expected_type, type(cmd))

    async def test_private_mounts(self, m_curtin_command_init):
        await start_curtin_command(
            self.app,
            mock.Mock(),
            "in-target",
            "--target",
            "/target",
            "--",
            "/bin/ls",
            private_mounts=True,
        )

        m_curtin_command_init.assert_called_once_with(
            self.app.opts,
            self.app.command_runner,
            "in-target",
            "--target",
            "/target",
            "--",
            "/bin/ls",
            config=None,
            runner_kwargs={"private_mounts": True},
        )

    async def test_runner(self, m_curtin_command_init):
        runner = mock.Mock()
        await start_curtin_command(
            self.app,
            mock.Mock(),
            "in-target",
            "--target",
            "/target",
            "--",
            "/bin/ls",
            runner=runner,
            private_mounts=False,
        )

        m_curtin_command_init.assert_called_once_with(
            self.app.opts,
            runner,
            "in-target",
            "--target",
            "/target",
            "--",
            "/bin/ls",
            config=None,
            runner_kwargs={},
        )

    async def test_private_mounts_incompatible_runner(self, m_curtin_command_init):
        with self.assertRaises(NotImplementedError):
            await start_curtin_command(
                self.app,
                mock.Mock(),
                "in-target",
                "--target",
                "/target",
                "--",
                "/bin/ls",
                runner=mock.Mock(),
                private_mounts=True,
            )

        m_curtin_command_init.assert_not_called()
