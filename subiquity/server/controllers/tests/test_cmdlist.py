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

from unittest import IsolatedAsyncioTestCase, mock

from subiquity.server.controllers import cmdlist
from subiquity.server.controllers.cmdlist import (
    CmdListController,
    Command,
    EarlyController,
    LateController,
)
from subiquitycore.tests.mocks import make_app
from subiquitycore.utils import orig_environ


@mock.patch.object(cmdlist, "orig_environ", side_effect=orig_environ)
@mock.patch.object(cmdlist, "arun_command")
class TestCmdListController(IsolatedAsyncioTestCase):
    controller_type = CmdListController

    def setUp(self):
        self.controller = self.controller_type(make_app())
        self.controller.cmds = [Command(args="some-command", check=False)]
        snap_env = {
            "LD_LIBRARY_PATH": "/var/lib/snapd/lib/gl",
        }
        self.mocked_os_environ = mock.patch.dict("os.environ", snap_env)

    @mock.patch("shutil.which", return_value="/usr/bin/path/to/bin")
    async def test_no_snap_env_on_call(
        self,
        mocked_shutil,
        mocked_arun,
        mocked_orig_environ,
    ):
        with self.mocked_os_environ:
            await self.controller.run()
            args, kwargs = mocked_arun.call_args
            call_env = kwargs["env"]

            mocked_orig_environ.assert_called()
            self.assertNotIn("LD_LIBRARY_PATH", call_env)

    @mock.patch("shutil.which", return_value="/snap/path/to/bin")
    async def test_with_snap_env_on_call(
        self,
        mocked_shutil,
        mocked_arun,
        mocked_orig_environ,
    ):
        with self.mocked_os_environ:
            await self.controller.run()
            args, kwargs = mocked_arun.call_args
            call_env = kwargs["env"]

            mocked_orig_environ.assert_not_called()
            self.assertIn("LD_LIBRARY_PATH", call_env)


class TestEarlyController(TestCmdListController):
    controller_type = EarlyController

    def setUp(self):
        super().setUp()


class TestLateController(TestCmdListController):
    controller_type = LateController

    def setUp(self):
        super().setUp()
