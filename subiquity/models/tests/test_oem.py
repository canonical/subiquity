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

from unittest import mock

from subiquity.common.os import UbuntuInfo
from subiquity.models.oem import OEMModel
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.parameterized import parameterized


class TestOEMModel(SubiTestCase):
    @parameterized.expand(
        [
            ["26.04", "server", True],
            ["26.04", "desktop", True],
            ["26.04", "core", False],
            ["25.10", "server", False],
            ["24.04", "server", False],
            ["24.04", "desktop", True],
        ]
    )
    def test_install_on(self, series, variant, expected):
        ubuntu_info = UbuntuInfo(
            codename="mock-codename",
            release=series,
            pretty_name="mock-pretty-name",
        )

        with mock.patch(
            "subiquity.models.oem.read_ubuntu_info", return_value=ubuntu_info
        ):
            model = OEMModel(dry_run=False)
            self.assertEqual(expected, model.install_on[variant])
