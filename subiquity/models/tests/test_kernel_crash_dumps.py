# Copyright 2024 Canonical, Ltd.
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

from subiquity.models.kernel_crash_dumps import KernelCrashDumpsModel
from subiquitycore.tests import SubiTestCase


class TestKernelCrashDumpsModel(SubiTestCase):
    def setUp(self):
        self.model = KernelCrashDumpsModel()

    def test_automatic_decision(self):
        """Test the curtin config for curtin automatic enablement."""
        expected = {"kernel-crash-dumps": {"enabled": None}}
        self.assertEqual(expected, self.model.render())

    def test_render_formatting(self):
        """Test the curtin config populates with correct formatting."""
        config = {}
        self.model.enabled = config["enabled"] = True
        expected = {"kernel-crash-dumps": config}
        self.assertEqual(expected, self.model.render())
