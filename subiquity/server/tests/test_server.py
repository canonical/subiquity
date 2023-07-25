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
import shlex
from unittest.mock import Mock, patch

from subiquity.common.types import PasswordKind
from subiquity.server.server import (
    MetaController,
    SubiquityServer,
    cloud_autoinstall_path,
    iso_autoinstall_path,
    root_autoinstall_path,
)
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.utils import run_command


class TestAutoinstallLoad(SubiTestCase):
    async def asyncSetUp(self):
        self.tempdir = self.tmp_dir()
        os.makedirs(self.tempdir + "/cdrom", exist_ok=True)
        opts = Mock()
        opts.dry_run = True
        opts.output_base = self.tempdir
        opts.machine_config = "examples/machines/simple.json"
        opts.kernel_cmdline = {}
        opts.autoinstall = None
        self.server = SubiquityServer(opts, None)
        self.server.base_model = Mock()
        self.server.base_model.root = opts.output_base

    def path(self, relative_path):
        return self.tmp_path(relative_path, dir=self.tempdir)

    def create(self, path, contents):
        path = self.path(path)
        with open(path, "w") as fp:
            fp.write(contents)
        return path

    def test_autoinstall_disabled(self):
        self.create(root_autoinstall_path, "root")
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.server.opts.autoinstall = ""
        self.assertIsNone(self.server.select_autoinstall())

    def test_root_wins(self):
        root = self.create(root_autoinstall_path, "root")
        autoinstall = self.create(self.path("arg.autoinstall.yaml"), "arg")
        self.server.opts.autoinstall = autoinstall
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "root")

    def test_arg_wins(self):
        root = self.path(root_autoinstall_path)
        arg = self.create(self.path("arg.autoinstall.yaml"), "arg")
        self.server.opts.autoinstall = arg
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "arg")

    def test_cloud_wins(self):
        root = self.path(root_autoinstall_path)
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "cloud")

    def test_iso_wins(self):
        root = self.path(root_autoinstall_path)
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "iso")

    def test_nobody_wins(self):
        self.assertIsNone(self.server.select_autoinstall())

    def test_bogus_autoinstall_argument(self):
        self.server.opts.autoinstall = self.path("nonexistant.yaml")
        with self.assertRaises(Exception):
            self.server.select_autoinstall()

    def test_early_commands_changes_autoinstall(self):
        self.server.controllers = Mock()
        self.server.controllers.instances = []
        rootpath = self.path(root_autoinstall_path)

        cmd = f"sed -i -e '$ a stuff: things' {rootpath}"
        contents = f"""\
version: 1
early-commands: ["{cmd}"]
"""
        arg = self.create(self.path("arg.autoinstall.yaml"), contents)
        self.server.opts.autoinstall = arg

        self.server.autoinstall = self.server.select_autoinstall()
        self.server.load_autoinstall_config(only_early=True)
        before_early = {"version": 1, "early-commands": [cmd]}
        self.assertEqual(before_early, self.server.autoinstall_config)
        run_command(shlex.split(cmd), check=True)

        self.server.load_autoinstall_config(only_early=False)
        after_early = {"version": 1, "early-commands": [cmd], "stuff": "things"}
        self.assertEqual(after_early, self.server.autoinstall_config)


class TestMetaController(SubiTestCase):
    async def test_interactive_sections_not_present(self):
        mc = MetaController(make_app())
        mc.app.autoinstall_config = None
        self.assertIsNone(await mc.interactive_sections_GET())

    async def test_interactive_sections_empty(self):
        mc = MetaController(make_app())
        mc.app.autoinstall_config["interactive-sections"] = []
        self.assertEqual([], await mc.interactive_sections_GET())

    async def test_interactive_sections_all(self):
        mc = MetaController(make_app())
        mc.app.autoinstall_config["interactive-sections"] = ["*"]
        mc.app.controllers.instances = [
            Mock(autoinstall_key="f", interactive=Mock(return_value=False)),
            Mock(autoinstall_key=None, interactive=Mock(return_value=True)),
            Mock(autoinstall_key="t", interactive=Mock(return_value=True)),
        ]
        self.assertEqual(["t"], await mc.interactive_sections_GET())

    async def test_interactive_sections_one(self):
        mc = MetaController(make_app())
        mc.app.autoinstall_config["interactive-sections"] = ["network"]
        self.assertEqual(["network"], await mc.interactive_sections_GET())


class TestDefaultUser(SubiTestCase):
    @patch(
        "subiquity.server.server.ug_util.normalize_users_groups",
        Mock(return_value=(None, None)),
    )
    @patch(
        "subiquity.server.server.ug_util.extract_default",
        Mock(return_value=(None, None)),
    )
    @patch(
        "subiquity.server.server.user_key_fingerprints",
        Mock(side_effect=Exception("should not be called")),
    )
    async def test_no_default_user(self):
        opts = Mock()
        opts.dry_run = True
        opts.output_base = self.tmp_dir()
        opts.machine_config = "examples/machines/simple.json"
        server = SubiquityServer(opts, None)
        server.cloud = Mock()
        server._user_has_password = Mock(side_effect=Exception("should not be called"))

        opts.dry_run = False  # exciting!
        server.set_installer_password()
        self.assertIsNone(server.installer_user_name)
        self.assertEqual(PasswordKind.NONE, server.installer_user_passwd_kind)
