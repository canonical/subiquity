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

import unittest

from subiquity.common.types import (
    GuidedCapability,
    SizingPolicy,
)


class TestSizingPolicy(unittest.TestCase):
    def test_all(self):
        actual = SizingPolicy.from_string('all')
        self.assertEqual(SizingPolicy.ALL, actual)

    def test_scaled_size(self):
        actual = SizingPolicy.from_string('scaled')
        self.assertEqual(SizingPolicy.SCALED, actual)

    def test_default(self):
        actual = SizingPolicy.from_string(None)
        self.assertEqual(SizingPolicy.SCALED, actual)


class TestCapabilities(unittest.TestCase):
    def test_not_zfs(self):
        self.assertFalse(GuidedCapability.DIRECT.is_zfs())

    def test_is_zfs(self):
        self.assertTrue(GuidedCapability.ZFS.is_zfs())
