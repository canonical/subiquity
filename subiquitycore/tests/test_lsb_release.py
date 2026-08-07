# Copyright 2021 Canonical, Ltd.
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
from pathlib import Path
from unittest.mock import patch

from subiquitycore.lsb_release import LSB_RELEASE_EXAMPLE, LSB_RELEASE_FILE, lsb_release


class TestLSBRelease(unittest.TestCase):
    def setUp(self):
        self.lsb_str = """
    def test_lsb_release(self):
DISTRIB_ID=Ubuntu
DISTRIB_RELEASE=21.10
DISTRIB_CODENAME=impish
DISTRIB_DESCRIPTION="Ubuntu 21.10"
        """

    def test_lsb_release(self):
        with patch.object(Path, "read_text", autospec=True, return_value=self.lsb_str):
            distro = lsb_release(path=Path("sample"))

        self.assertEqual(distro["id"], "Ubuntu")
        self.assertEqual(distro["release"], "21.10")
        self.assertEqual(distro["codename"], "impish")
        self.assertEqual(distro["description"], "Ubuntu 21.10")

    def test_lsb_release_inexistent(self):
        with patch.object(
            Path, "read_text", autospec=True, side_effect=FileNotFoundError
        ) as patched:
            self.assertEqual(lsb_release(Path("/inexistent")), {})
        self.assertEqual(Path("/inexistent"), patched.call_args.args[0])

    def test_lsb_release_default(self):
        with patch.object(
            Path, "read_text", autospec=True, return_value=self.lsb_str
        ) as patched:
            lsb_release(path=None)
        self.assertEqual(LSB_RELEASE_FILE, patched.call_args.args[0])

    def test_lsb_release_dry_run(self):
        with patch.object(
            Path, "read_text", autospec=True, return_value=self.lsb_str
        ) as patched:
            lsb_release(dry_run=True)
        self.assertEqual(LSB_RELEASE_EXAMPLE, patched.call_args.args[0])

    def test_lsb_release_mutually_exclusive(self):
        with self.assertRaises(ValueError):
            lsb_release(path=Path("sample"), dry_run=True)
