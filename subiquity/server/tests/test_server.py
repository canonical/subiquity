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

from unittest.mock import Mock

from subiquitycore.tests import SubiTestCase
from subiquity.server.server import (
    SubiquityServer,
    cloud_autoinstall_path,
    iso_autoinstall_path,
    reload_autoinstall_path,
)


class TestAutoinstallLoad(SubiTestCase):
    def setUp(self):
        self.tempdir = self.tmp_dir()
        opts = Mock()
        opts.dry_run = True
        opts.output_base = self.tempdir
        opts.machine_config = 'examples/simple.json'
        opts.kernel_cmdline = ''
        opts.autoinstall = None
        self.server = SubiquityServer(opts, None)
        self.server.base_model = Mock()
        self.server.base_model.root = opts.output_base

    def path(self, relative_path):
        return self.tmp_path(relative_path, dir=self.tempdir)

    def create(self, path):
        path = self.path(path)
        open(path, 'w').close()
        return path

    def test_autoinstall_disabled(self):
        self.create(reload_autoinstall_path)
        self.create(cloud_autoinstall_path)
        self.create(iso_autoinstall_path)
        self.server.opts.autoinstall = ""
        self.assertIsNone(self.server.select_autoinstall_location())

    def test_reload_wins(self):
        expected = self.create(reload_autoinstall_path)
        autoinstall = self.create(self.path('arg.autoinstall.yaml'))
        self.server.opts.autoinstall = autoinstall
        self.create(cloud_autoinstall_path)
        self.create(iso_autoinstall_path)
        self.assertEqual(expected, self.server.select_autoinstall_location())

    def test_arg_wins(self):
        expected = self.create(self.path('arg.autoinstall.yaml'))
        self.server.opts.autoinstall = expected
        self.create(cloud_autoinstall_path)
        self.create(iso_autoinstall_path)
        self.assertEqual(expected, self.server.select_autoinstall_location())

    def test_cloud_wins(self):
        expected = self.create(cloud_autoinstall_path)
        self.create(iso_autoinstall_path)
        self.assertEqual(expected, self.server.select_autoinstall_location())

    def test_iso_wins(self):
        expected = self.create(iso_autoinstall_path)
        self.assertEqual(expected, self.server.select_autoinstall_location())

    def test_nobody_wins(self):
        self.assertIsNone(self.server.select_autoinstall_location())

    def test_copied_to_reload(self):
        self.server.autoinstall = self.tmp_path('test.yaml', dir=self.tempdir)
        expected = 'stuff things'
        with open(self.server.autoinstall, 'w') as fp:
            fp.write(expected)
        self.server.save_autoinstall_for_reload()
        with open(self.path(reload_autoinstall_path), 'r') as fp:
            self.assertEqual(expected, fp.read())

    def test_bogus_autoinstall_argument(self):
        self.server.opts.autoinstall = self.path('nonexistant.yaml')
        with self.assertRaises(Exception):
            self.server.select_autoinstall_location()
