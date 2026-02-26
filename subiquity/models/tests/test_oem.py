# Copyright 2026 Canonical, Ltd.
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

from contextlib import contextmanager
from unittest import mock

from subiquity.models.oem import OEMModel
from subiquitycore.lsb_release import lsb_release
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.parameterized import parameterized


class TestOEMModel(SubiTestCase):
    @contextmanager
    def patch_lsb_release(self, series):
        def fake_lsb_release(*args, **kwargs):
            return lsb_release(path=f"examples/lsb-release-{series}")

        with mock.patch(
            "subiquity.models.oem.lsb_release",
            wraps=fake_lsb_release,
        ):
            yield

    @parameterized.expand(
        [
            ["resolute", "server", True],
            ["resolute", "desktop", True],
            ["resolute", "core", False],
            ["questing", "server", False],
            ["noble", "server", False],
            ["noble", "desktop", True],
        ]
    )
    def test_install_on(self, series, variant, expected):
        with self.patch_lsb_release(series):
            model = OEMModel(dry_run=False)
            self.assertEqual(expected, model.install_on[variant])
