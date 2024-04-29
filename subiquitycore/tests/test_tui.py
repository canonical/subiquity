# Copyright 2023 Canonical, Ltd.
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

import json
import pathlib
from unittest.mock import Mock, patch

from subiquitycore.tests import SubiTestCase
from subiquitycore.tui import TuiApplication


class TestTuiApplication(SubiTestCase):
    def setUp(self):
        with patch("subiquitycore.tui.Application.__init__", return_value=None):
            opts = Mock()
            opts.answers = None
            opts.dry_run = True
            self.tui = TuiApplication(opts)
            # Usually, the below are assigned by Application.__init__()
            self.tui.opts = opts
            self.tui.state_dir = self.tmp_dir()

    def test_get_initial_rich_mode_normal(self):
        self.tui.opts.run_on_serial = False
        self.assertTrue(self.tui.get_initial_rich_mode())

        # With a state file.
        with (pathlib.Path(self.tui.state_dir) / "rich-mode-tty").open("w") as fh:
            fh.write(json.dumps(True))
        self.assertTrue(self.tui.get_initial_rich_mode())
        with (pathlib.Path(self.tui.state_dir) / "rich-mode-tty").open("w") as fh:
            fh.write(json.dumps(False))
        self.assertFalse(self.tui.get_initial_rich_mode())

    def test_get_initial_rich_mode_serial(self):
        self.tui.opts.run_on_serial = True
        self.assertFalse(self.tui.get_initial_rich_mode())

        # With a state file.
        with (pathlib.Path(self.tui.state_dir) / "rich-mode-serial").open("w") as fh:
            fh.write(json.dumps(True))
        self.assertTrue(self.tui.get_initial_rich_mode())
        with (pathlib.Path(self.tui.state_dir) / "rich-mode-serial").open("w") as fh:
            fh.write(json.dumps(False))
        self.assertFalse(self.tui.get_initial_rich_mode())

    def test_get_initial_rich_mode_legacy_state_file(self):
        # Make sure if an old rich-mode state file is present, it is honored -
        # but the new format takes precedence.
        self.tui.opts.run_on_serial = True
        with (pathlib.Path(self.tui.state_dir) / "rich-mode").open("w") as fh:
            fh.write(json.dumps(True))
        self.assertTrue(self.tui.get_initial_rich_mode())
        with (pathlib.Path(self.tui.state_dir) / "rich-mode-serial").open("w") as fh:
            fh.write(json.dumps(False))
        self.assertFalse(self.tui.get_initial_rich_mode())

        self.tui.opts.run_on_serial = False
        with (pathlib.Path(self.tui.state_dir) / "rich-mode").open("w") as fh:
            fh.write(json.dumps(False))
        self.assertFalse(self.tui.get_initial_rich_mode())
        with (pathlib.Path(self.tui.state_dir) / "rich-mode-tty").open("w") as fh:
            fh.write(json.dumps(True))
        self.assertTrue(self.tui.get_initial_rich_mode())
