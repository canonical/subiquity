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

from subiquity.models.drivers import DriversModel
from subiquitycore.tests.parameterized import parameterized


class TestDriversModel(unittest.TestCase):
    @parameterized.expand(
        (
            # no components
            ([], ["nvidia-driver-510"], []),
            # no drivers detected
            (["nvidia-510-uda-ko", "nvidia-510-uda-user"], [], []),
            # missing user component
            (["nvidia-510-uda-ko"], ["nvidia-driver-510"], []),
            # missing ko component
            (["nvidia-510-uda-user"], ["nvidia-driver-510"], []),
            # mismatched component versions, nothing usable available
            (
                ["nvidia-2-uda-ko", "nvidia-1-uda-user"],
                ["nvidia-driver-999"],
                [],
            ),
            # match
            (
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
                ["nvidia-driver-510"],
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
            ),
            # match, open driver
            (
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
                ["nvidia-driver-510-open"],
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
            ),
            # match, server driver
            (
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
                ["nvidia-driver-510-server"],
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
            ),
            # match, open server driver
            (
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
                ["nvidia-driver-510-server-open"],
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
            ),
            # match, open server driver, erd
            (
                ["nvidia-510-erd-ko", "nvidia-510-erd-user"],
                ["nvidia-driver-510-server-open"],
                ["nvidia-510-erd-ko", "nvidia-510-erd-user"],
            ),
            # prefer "newer" based on a reversed sort
            (
                [
                    "nvidia-1-uda-ko",
                    "nvidia-1-uda-user",
                    "nvidia-2-uda-ko",
                    "nvidia-2-uda-user",
                ],
                ["nvidia-driver-1", "nvidia-driver-2"],
                ["nvidia-2-uda-ko", "nvidia-2-uda-user"],
            ),
            (
                [
                    "nvidia-1-uda-ko",
                    "nvidia-1-uda-user",
                    "nvidia-2-uda-ko",
                    "nvidia-2-uda-user",
                ],
                ["nvidia-driver-2", "nvidia-driver-1"],
                ["nvidia-2-uda-ko", "nvidia-2-uda-user"],
            ),
            # wrong driver version
            (
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
                ["nvidia-driver-999"],
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
            ),
            # wrong driver version, erd
            (
                ["nvidia-510-erd-ko", "nvidia-510-erd-user"],
                ["nvidia-driver-999"],
                ["nvidia-510-erd-ko", "nvidia-510-erd-user"],
            ),
            # wrong driver version, use newer
            (
                [
                    "nvidia-1-uda-ko",
                    "nvidia-2-uda-user",
                    "nvidia-2-uda-ko",
                    "nvidia-1-uda-user",
                ],
                ["nvidia-driver-999"],
                ["nvidia-2-uda-ko", "nvidia-2-uda-user"],
            ),
            # mismatched component versions, something usable available
            (
                ["nvidia-1-uda-ko", "nvidia-2-uda-ko", "nvidia-1-uda-user"],
                ["nvidia-driver-999"],
                ["nvidia-1-uda-ko", "nvidia-1-uda-user"],
            ),
            # branch mismatch
            (
                ["nvidia-1-uda-ko", "nvidia-1-erd-user"],
                ["nvidia-driver-999"],
                [],
            ),
        )
    )
    def test_matching_kernel_components(self, comps, drivers, expected):
        self.model = DriversModel()
        self.model.deb_drivers = drivers
        self.assertEqual(expected, self.model.matching_kernel_components(comps))
