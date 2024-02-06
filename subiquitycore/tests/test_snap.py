# Copyright 2024 Canonical, Ltd.
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
from unittest.mock import patch

from subiquitycore import snap


class TestSnap(unittest.TestCase):
    @patch("os.getenv", return_value=None)
    def test_is_snap(self, os_getenv):
        self.assertFalse(snap.is_snap())
        os_getenv.assert_called_with("SNAP_CONFINEMENT")
        os_getenv.reset_mock()

        os_getenv.return_value = "strict"
        self.assertTrue(snap.is_snap())
        os_getenv.assert_called_with("SNAP_CONFINEMENT")
        os_getenv.reset_mock()

        os_getenv.return_value = "classic"
        self.assertTrue(snap.is_snap())
        os_getenv.assert_called_with("SNAP_CONFINEMENT")
        os_getenv.reset_mock()

    @patch("os.getenv", return_value=None)
    def test_snap_confinement(self, os_getenv):
        self.assertFalse(snap.is_snap_strictly_confined())
        os_getenv.assert_called_with("SNAP_CONFINEMENT", "classic")
        os_getenv.reset_mock()

        os_getenv.return_value = "strict"
        self.assertTrue(snap.is_snap_strictly_confined())

        os_getenv.return_value = "classic"
        self.assertFalse(snap.is_snap_strictly_confined())

    @patch("os.getenv", return_value=None)
    def test_snap_name(self, os_getenv):
        self.assertIsNone(snap.snap_name())
        os_getenv.assert_called_with("SNAP_INSTANCE_NAME")
        os_getenv.reset_mock()

        os_getenv.return_value = "console-conf"
        self.assertEqual(snap.snap_name(), "console-conf")
