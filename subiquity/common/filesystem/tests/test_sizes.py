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
from unittest import mock

from subiquity.common.filesystem.sizes import (
    bootfs_scale,
    calculate_guided_resize,
    calculate_suggested_install_min,
    get_efi_size,
    get_bootfs_size,
    PartitionScaleFactors,
    scale_partitions,
    uefi_scale,
    )
from subiquity.common.types import GuidedResizeValues


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
        tests = [
            # something large to hit maximums
            (30 << 30, uefi_scale.maximum, bootfs_scale.maximum),
            # and something small to hit minimums
            (8 << 30, uefi_scale.minimum, bootfs_scale.minimum),
        ]
        for disk_size, uefi, bootfs in tests:
            self.assertEqual(uefi, get_efi_size(disk_size))
            self.assertEqual(bootfs, get_bootfs_size(disk_size))

        # something in between for scaling
        disk_size = 20 << 30
        efi_size = get_efi_size(disk_size)
        self.assertTrue(uefi_scale.maximum > efi_size)
        self.assertTrue(efi_size > uefi_scale.minimum)
        bootfs_size = get_bootfs_size(disk_size)
        self.assertTrue(bootfs_scale.maximum > bootfs_size)
        self.assertTrue(bootfs_size > bootfs_scale.minimum)


class TestCalculateGuidedResize(unittest.TestCase):
    def test_ignore_nonresizable(self):
        actual = calculate_guided_resize(
                part_min=-1, part_size=100 << 30, install_min=10 << 30)
        self.assertIsNone(actual)

    def test_too_small(self):
        actual = calculate_guided_resize(
                part_min=95 << 30, part_size=100 << 30, install_min=10 << 30)
        self.assertIsNone(actual)

    def test_even_split(self):
        # 8 GiB * 1.25 == 10 GiB
        size = 10 << 30
        actual = calculate_guided_resize(
                part_min=8 << 30, part_size=100 << 30, install_min=size)
        expected = GuidedResizeValues(
                install_max=(100 << 30) - size,
                minimum=size, recommended=50 << 30, maximum=(100 << 30) - size)
        self.assertEqual(expected, actual)

    def test_weighted_split(self):
        actual = calculate_guided_resize(
                part_min=40 << 30, part_size=240 << 30, install_min=10 << 30)
        expected = GuidedResizeValues(
                install_max=190 << 30,
                minimum=50 << 30, recommended=200 << 30, maximum=230 << 30)
        self.assertEqual(expected, actual)


class TestCalculateInstallMin(unittest.TestCase):
    @mock.patch('subiquity.common.filesystem.sizes.swap.suggested_swapsize')
    @mock.patch('subiquity.common.filesystem.sizes.bootfs_scale')
    def test_small_setups(self, bootfs_scale, swapsize):
        swapsize.return_value = 1 << 30
        bootfs_scale.maximum = 1 << 30
        source_min = 1 << 30
        # with a small source, we hit the default 2GiB padding
        self.assertEqual(5 << 30, calculate_suggested_install_min(source_min))

    @mock.patch('subiquity.common.filesystem.sizes.swap.suggested_swapsize')
    @mock.patch('subiquity.common.filesystem.sizes.bootfs_scale')
    def test_small_setups_big_swap(self, bootfs_scale, swapsize):
        swapsize.return_value = 10 << 30
        bootfs_scale.maximum = 1 << 30
        source_min = 1 << 30
        self.assertEqual(14 << 30, calculate_suggested_install_min(source_min))

    @mock.patch('subiquity.common.filesystem.sizes.swap.suggested_swapsize')
    @mock.patch('subiquity.common.filesystem.sizes.bootfs_scale')
    def test_small_setups_big_boot(self, bootfs_scale, swapsize):
        swapsize.return_value = 1 << 30
        bootfs_scale.maximum = 10 << 30
        source_min = 1 << 30
        self.assertEqual(14 << 30, calculate_suggested_install_min(source_min))

    @mock.patch('subiquity.common.filesystem.sizes.swap.suggested_swapsize')
    @mock.patch('subiquity.common.filesystem.sizes.bootfs_scale')
    def test_big_source(self, bootfs_scale, swapsize):
        swapsize.return_value = 1 << 30
        bootfs_scale.maximum = 2 << 30
        source_min = 10 << 30
        # a bigger source should hit 80% padding
        expected = (10 + 8 + 1 + 2) << 30
        self.assertEqual(expected, calculate_suggested_install_min(source_min))
