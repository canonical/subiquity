# Copyright 2021 Canonical, Ltd.
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

import unittest
from unittest.mock import mock_open, patch

from subiquitycore.lsb_release import lsb_release


class TestLSBRelease(unittest.TestCase):
    def setUp(self):
        self.target = "subiquitycore.lsb_release.open"

    def test_lsb_release(self):
        lsb_str = """
DISTRIB_ID=Ubuntu
DISTRIB_RELEASE=21.10
DISTRIB_CODENAME=impish
DISTRIB_DESCRIPTION="Ubuntu 21.10"
        """

        with patch(self.target, mock_open(read_data=lsb_str)) as patched:
            distro = lsb_release(path="sample")
            patched.assert_called_once_with("sample", "r")
            self.assertEqual(distro["id"], "Ubuntu")
            self.assertEqual(distro["release"], "21.10")
            self.assertEqual(distro["codename"], "impish")
            self.assertEqual(distro["description"], "Ubuntu 21.10")

    def test_lsb_release_inexistent(self):
        with patch(self.target, side_effect=FileNotFoundError):
            self.assertEqual(lsb_release("/inexistent"), {})

    def test_lsb_release_default(self):
        with patch(self.target, side_effect=FileNotFoundError) as patched:
            lsb_release(path=None)
            patched.assert_called_once_with("/etc/lsb-release", "r")

    def test_lsb_release_dry_run(self):
        with patch(self.target, side_effect=FileNotFoundError) as patched:
            lsb_release(dry_run=True)
            patched.assert_called_once_with("examples/lsb-release-focal", "r")

    def test_lsb_release_mutually_exclusive(self):
        with self.assertRaises(ValueError):
            lsb_release(path="sample", dry_run=True)
