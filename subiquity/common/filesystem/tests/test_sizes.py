# Copyright 2022 Canonical, Ltd.
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

from subiquity.common.filesystem.sizes import (
    bootfs_scale,
    get_efi_size,
    get_bootfs_size,
    PartitionScaleFactors,
    scale_partitions,
    uefi_scale,
    )
from subiquity.common.filesystem.tests.test_manipulator import make_manipulator
from subiquity.models.filesystem import Bootloader
from subiquity.models.tests.test_filesystem import make_disk


class TestPartitionSizeScaling(unittest.TestCase):
    def test_scale_factors(self):
        psf = [
            PartitionScaleFactors(minimum=100, priority=500, maximum=500),
            PartitionScaleFactors(minimum=1000, priority=9500, maximum=-1),
        ]

        # match priorities, should get same values back
        self.assertEqual([500, 9500], scale_partitions(psf, 10000))

        # half priorities, should be scaled
        self.assertEqual([250, 4750], scale_partitions(psf, 5000))

        # hit max on first partition, second should use rest of space
        self.assertEqual([500, 19500], scale_partitions(psf, 20000))

        # minimums
        self.assertEqual([100, 1000], scale_partitions(psf, 1100))

        # ints
        self.assertEqual([105, 1996], scale_partitions(psf, 2101))

    def test_no_max_equal_minus_one(self):
        psf = [
            PartitionScaleFactors(minimum=100, priority=500, maximum=500),
            PartitionScaleFactors(minimum=100, priority=500, maximum=500),
        ]

        self.assertEqual([500, 500], scale_partitions(psf, 2000))

    def test_efi(self):
        manipulator = make_manipulator(Bootloader.UEFI)
        tests = [
            # something large to hit maximums
            (30 << 30, uefi_scale.maximum, bootfs_scale.maximum),
            # and something small to hit minimums
            (8 << 30, uefi_scale.minimum, bootfs_scale.minimum),
        ]
        for disk_size, uefi, bootfs in tests:
            disk = make_disk(manipulator.model, preserve=True, size=disk_size)
            self.assertEqual(uefi, get_efi_size(disk))
            self.assertEqual(bootfs, get_bootfs_size(disk))

        # something in between for scaling
        disk_size = 20 << 30
        disk = make_disk(manipulator.model, preserve=True, size=disk_size)
        efi_size = get_efi_size(disk)
        self.assertTrue(uefi_scale.maximum > efi_size)
        self.assertTrue(efi_size > uefi_scale.minimum)
        bootfs_size = get_bootfs_size(disk)
        self.assertTrue(bootfs_scale.maximum > bootfs_size)
        self.assertTrue(bootfs_size > bootfs_scale.minimum)
