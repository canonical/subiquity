# Copyright 2025 Canonical, Ltd.
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
from unittest.mock import Mock, patch

from subiquity.server.snapd.info import SnapdInfo, SnapdVersion


class TestSnapdInfo(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.info = SnapdInfo(Mock())

    def test_parse_version__major_minor(self):
        self.assertEqual(SnapdVersion(2, 68), self.info._parse_version("2.68"))

    def test_parse_version__major_minor_patch(self):
        self.assertEqual(SnapdVersion(2, 68, 4), self.info._parse_version("2.68.4"))

    def test_parse_version__major_minor_git_version(self):
        self.assertEqual(
            SnapdVersion(2, 70, 0), self.info._parse_version("2.70+g59.0e89e83")
        )

    def test_parse_version__major_minor_patch_git_version(self):
        self.assertEqual(
            SnapdVersion(2, 68, 1), self.info._parse_version("2.68.1+g59.0e89e83")
        )

    def test_parse_version__bad_version(self):
        with self.assertRaises(ValueError):
            self.info._parse_version("2.+g59.0e89e83")

    async def test_has_beta_entropy__yes_equal(self):
        with patch.object(self.info, "version", return_value=SnapdVersion(2, 68)):
            self.assertTrue(await self.info.has_beta_entropy_check())

    async def test_has_beta_entropy__yes_greater(self):
        with patch.object(self.info, "version", return_value=SnapdVersion(2, 68, 4)):
            self.assertTrue(await self.info.has_beta_entropy_check())

    async def test_has_beta_entropy__no(self):
        with patch.object(self.info, "version", return_value=SnapdVersion(2, 67)):
            self.assertFalse(await self.info.has_beta_entropy_check())
