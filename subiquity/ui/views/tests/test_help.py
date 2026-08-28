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

from subiquity.ui.views.help import HelpMenu


class HelpMenuTests(unittest.TestCase):
    def test__default_about_msg(self):
        # Regression test for the AttributeError raised when
        # _default_about_msg treated the UbuntuInfo returned by
        # read_ubuntu_info() as a dict.
        # LP: #2165329
        app = mock.Mock()
        # dry-run loads examples/os-release-stonking (Ubuntu 26.10).
        app.opts.dry_run = True
        menu = HelpMenu(app)
        msg = menu._default_about_msg()
        self.assertIn("26.10", msg)
