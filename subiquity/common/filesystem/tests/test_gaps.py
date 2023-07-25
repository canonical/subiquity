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
from functools import partial
from unittest import mock

from subiquity.common.filesystem import gaps
from subiquity.common.types import GapUsable
from subiquity.models.filesystem import (
    LVM_CHUNK_SIZE,
    LVM_OVERHEAD,
    Disk,
    MiB,
    PartitionAlignmentData,
    Raid,
)
from subiquity.models.tests.test_filesystem import (
    make_disk,
    make_lv,
    make_model,
    make_model_and_disk,
    make_model_and_lv,
    make_partition,
    make_vg,
)
from subiquitycore.tests.parameterized import parameterized


class GapTestCase(unittest.TestCase):
    def use_alignment_data(self, alignment_data):
        m = mock.patch("subiquity.common.filesystem.gaps.parts_and_gaps")
        p = m.start()
        self.addCleanup(m.stop)
        p.side_effect = partial(gaps.find_disk_gaps_v2, info=alignment_data)

        for cls in Disk, Raid:
            md = mock.patch.object(cls, "alignment_data")
            p = md.start()
            self.addCleanup(md.stop)
            p.return_value = alignment_data


class TestGaps(unittest.TestCase):
    def test_basic(self):
        [gap] = gaps.parts_and_gaps(make_disk())
        self.assertTrue(isinstance(gap, gaps.Gap))
        self.assertEqual(MiB, gap.offset)


class TestSplitGap(GapTestCase):
    def test_equal(self):
        [gap] = gaps.parts_and_gaps(make_disk())
        actual = gap.split(gap.size)
        self.assertEqual((gap, None), actual)

    def test_too_big(self):
        [gap] = gaps.parts_and_gaps(make_disk())
        with self.assertRaises(ValueError):
            gap.split(gap.size + MiB)

    def test_split(self):
        [gap] = gaps.parts_and_gaps(make_disk(size=100 << 30))
        size = 10 << 30
        new_gaps = gap.split(size)
        self.assertEqual(2, len(new_gaps))
        self.assertEqual(size, new_gaps[0].size)
        self.assertEqual(gap.size - size, new_gaps[1].size)
        self.assertEqual(gap.offset, new_gaps[0].offset)
        self.assertEqual(gap.offset + size, new_gaps[1].offset)

    @parameterized.expand([[1], [10]])
    def test_split_in_extended(self, ebr_space):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=1,
                min_gap_size=1,
                min_start_offset=0,
                min_end_offset=0,
                primary_part_limit=4,
                ebr_space=ebr_space,
            )
        )

        m = make_model(storage_version=2)
        d = make_disk(m, size=100, ptable="dos")
        [gap] = gaps.parts_and_gaps(d)
        make_partition(m, d, offset=gap.offset, size=gap.size, flag="extended")
        [p, g] = gaps.parts_and_gaps(d)
        self.assertTrue(g.in_extended)
        g1, g2 = g.split(10)
        self.assertEqual(g1.offset + g1.size + ebr_space, g2.offset)


class TestAtOffset(unittest.TestCase):
    def test_zero(self):
        self.assertIsNone(gaps.at_offset(make_disk(), 0))

    def test_match(self):
        [gap] = gaps.parts_and_gaps(make_disk())
        self.assertEqual(gap, gaps.at_offset(gap.device, gap.offset))

    def test_not_match(self):
        [gap] = gaps.parts_and_gaps(make_disk())
        self.assertIsNone(gaps.at_offset(gap.device, gap.offset + 1))

    def test_two_gaps(self):
        m, d = make_model_and_disk(size=100 << 20)
        m.storage_version = 2
        make_partition(m, d, offset=0, size=20 << 20)
        make_partition(m, d, offset=40 << 20, size=20 << 20)
        [_, g1, _, g2] = gaps.parts_and_gaps(d)
        self.assertEqual(g1, gaps.at_offset(d, 20 << 20))
        self.assertEqual(g2, gaps.at_offset(d, 60 << 20))


class TestWithin(unittest.TestCase):
    def test_identity(self):
        d = make_disk()
        [gap] = gaps.parts_and_gaps(d)
        self.assertEqual(gap, gap.within())

    def test_front_used(self):
        m, d = make_model_and_disk(size=200 << 20)
        m.storage_version = 2
        make_partition(m, d, offset=100 << 20, size=1 << 20)
        [orig_g1, p1, orig_g2] = gaps.parts_and_gaps(d)
        make_partition(m, d, offset=0, size=20 << 20)
        [p1, g1, p2, g2] = gaps.parts_and_gaps(d)
        self.assertEqual(g1, orig_g1.within())

    def test_back_used(self):
        m, d = make_model_and_disk(size=200 << 20)
        m.storage_version = 2
        make_partition(m, d, offset=100 << 20, size=1 << 20)
        [orig_g1, p1, orig_g2] = gaps.parts_and_gaps(d)
        make_partition(m, d, offset=80 << 20, size=20 << 20)
        [g1, p1, p2, g2] = gaps.parts_and_gaps(d)
        self.assertEqual(g1, orig_g1.within())

    def test_front_and_back_used(self):
        m, d = make_model_and_disk(size=200 << 20)
        m.storage_version = 2
        make_partition(m, d, offset=100 << 20, size=1 << 20)
        [orig_g1, p1, orig_g2] = gaps.parts_and_gaps(d)
        make_partition(m, d, offset=0, size=20 << 20)
        make_partition(m, d, offset=80 << 20, size=20 << 20)
        [p1, g1, p2, p3, g2] = gaps.parts_and_gaps(d)
        self.assertEqual(g1, orig_g1.within())

    def test_multi_gap(self):
        m, d = make_model_and_disk(size=200 << 20)
        m.storage_version = 2
        make_partition(m, d, offset=100 << 20, size=1 << 20)
        [orig_g1, p1, orig_g2] = gaps.parts_and_gaps(d)
        make_partition(m, d, offset=20 << 20, size=20 << 20)
        [g1, p1, g2, p2, g3] = gaps.parts_and_gaps(d)
        self.assertEqual(g1, orig_g1.within())

    def test_later_part_of_disk(self):
        m, d = make_model_and_disk(size=200 << 20)
        m.storage_version = 2
        make_partition(m, d, offset=100 << 20, size=1 << 20)
        [orig_g1, p1, orig_g2] = gaps.parts_and_gaps(d)
        make_partition(m, d, offset=120 << 20, size=20 << 20)
        [g1, p1, g2, p2, g3] = gaps.parts_and_gaps(d)
        self.assertEqual(g2, orig_g2.within())


class TestAfter(unittest.TestCase):
    def test_basic(self):
        d = make_disk()
        [gap] = gaps.parts_and_gaps(d)
        self.assertEqual(gap, gaps.after(d, 0))

    def test_no_equals(self):
        d = make_disk()
        [gap] = gaps.parts_and_gaps(d)
        self.assertIsNone(gaps.after(d, gap.offset))

    def test_partition_resize_full_part(self):
        m, d = make_model_and_disk()
        [g1] = gaps.parts_and_gaps(d)
        p1 = make_partition(m, d, size=g1.size)
        p1.size //= 2
        gap = gaps.after(d, p1.offset)
        self.assertIsNotNone(gap)

    def test_partition_resize_half_part(self):
        m, d = make_model_and_disk()
        make_partition(m, d)
        [p1, g1] = gaps.parts_and_gaps(d)
        p1.size //= 2
        gap = gaps.after(d, p1.offset)
        self.assertNotEqual(gap, g1)
        self.assertTrue(gap.offset < g1.offset)


class TestDiskGaps(unittest.TestCase):
    def test_no_partition_gpt(self):
        size = 1 << 30
        d = make_disk(size=size, ptable="gpt")
        self.assertEqual(
            gaps.find_disk_gaps_v2(d), [gaps.Gap(d, MiB, size - 2 * MiB, False)]
        )

    def test_no_partition_dos(self):
        size = 1 << 30
        d = make_disk(size=size, ptable="dos")
        self.assertEqual(
            gaps.find_disk_gaps_v2(d), [gaps.Gap(d, MiB, size - MiB, False)]
        )

    def test_all_partition(self):
        info = PartitionAlignmentData(
            part_align=10,
            min_gap_size=1,
            min_start_offset=0,
            min_end_offset=0,
            primary_part_limit=10,
        )
        m, d = make_model_and_disk(size=100)
        p = make_partition(m, d, offset=0, size=100)
        self.assertEqual(gaps.find_disk_gaps_v2(d, info), [p])

    def test_all_partition_with_min_offsets(self):
        info = PartitionAlignmentData(
            part_align=10,
            min_gap_size=1,
            min_start_offset=10,
            min_end_offset=10,
            primary_part_limit=10,
        )
        m, d = make_model_and_disk(size=100)
        p = make_partition(m, d, offset=10, size=80)
        self.assertEqual(gaps.find_disk_gaps_v2(d, info), [p])

    def test_half_partition(self):
        info = PartitionAlignmentData(
            part_align=10,
            min_gap_size=1,
            min_start_offset=0,
            min_end_offset=0,
            primary_part_limit=10,
        )
        m, d = make_model_and_disk(size=100)
        p = make_partition(m, d, offset=0, size=50)
        self.assertEqual(gaps.find_disk_gaps_v2(d, info), [p, gaps.Gap(d, 50, 50)])

    def test_gap_in_middle(self):
        info = PartitionAlignmentData(
            part_align=10,
            min_gap_size=1,
            min_start_offset=0,
            min_end_offset=0,
            primary_part_limit=10,
        )
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=0, size=20)
        p2 = make_partition(m, d, offset=80, size=20)
        self.assertEqual(gaps.find_disk_gaps_v2(d, info), [p1, gaps.Gap(d, 20, 60), p2])

    def test_small_gap(self):
        info = PartitionAlignmentData(
            part_align=10,
            min_gap_size=20,
            min_start_offset=0,
            min_end_offset=0,
            primary_part_limit=10,
        )
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=0, size=40)
        p2 = make_partition(m, d, offset=50, size=50)
        self.assertEqual(gaps.find_disk_gaps_v2(d, info), [p1, p2])

    def test_align_gap(self):
        info = PartitionAlignmentData(
            part_align=10,
            min_gap_size=1,
            min_start_offset=0,
            min_end_offset=0,
            primary_part_limit=10,
        )
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=0, size=17)
        p2 = make_partition(m, d, offset=53, size=47)
        self.assertEqual(gaps.find_disk_gaps_v2(d, info), [p1, gaps.Gap(d, 20, 30), p2])

    def test_all_extended(self):
        info = PartitionAlignmentData(
            part_align=5,
            min_gap_size=1,
            min_start_offset=0,
            min_end_offset=0,
            ebr_space=2,
            primary_part_limit=10,
        )
        m, d = make_model_and_disk(size=100, ptable="dos")
        p = make_partition(m, d, offset=0, size=100, flag="extended")
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info),
            [
                p,
                gaps.Gap(d, 5, 95, True),
            ],
        )

    def test_half_extended(self):
        info = PartitionAlignmentData(
            part_align=5,
            min_gap_size=1,
            min_start_offset=0,
            min_end_offset=0,
            ebr_space=2,
            primary_part_limit=10,
        )
        m, d = make_model_and_disk(size=100)
        p = make_partition(m, d, offset=0, size=50, flag="extended")
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info),
            [p, gaps.Gap(d, 5, 45, True), gaps.Gap(d, 50, 50, False)],
        )

    def test_half_extended_one_logical(self):
        info = PartitionAlignmentData(
            part_align=5,
            min_gap_size=1,
            min_start_offset=0,
            min_end_offset=0,
            ebr_space=2,
            primary_part_limit=10,
        )
        m, d = make_model_and_disk(size=100, ptable="dos")
        p1 = make_partition(m, d, offset=0, size=50, flag="extended")
        p2 = make_partition(m, d, offset=5, size=45, flag="logical")
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info), [p1, p2, gaps.Gap(d, 50, 50, False)]
        )

    def test_half_extended_half_logical(self):
        info = PartitionAlignmentData(
            part_align=5,
            min_gap_size=1,
            min_start_offset=0,
            min_end_offset=0,
            ebr_space=2,
            primary_part_limit=10,
        )
        m, d = make_model_and_disk(size=100, ptable="dos")
        p1 = make_partition(m, d, offset=0, size=50, flag="extended")
        p2 = make_partition(m, d, offset=5, size=25, flag="logical")
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info),
            [
                p1,
                p2,
                gaps.Gap(d, 35, 15, True),
                gaps.Gap(d, 50, 50, False),
            ],
        )

    def test_gap_before_primary(self):
        # 0----10---20---30---40---50---60---70---80---90---100
        # [        g1             ][    p1 (primary)          ]
        info = PartitionAlignmentData(
            part_align=5,
            min_gap_size=1,
            min_start_offset=0,
            min_end_offset=0,
            ebr_space=1,
            primary_part_limit=10,
        )
        m, d = make_model_and_disk(size=100, ptable="dos")
        p1 = make_partition(m, d, offset=50, size=50)
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info), [gaps.Gap(d, 0, 50, False), p1]
        )

    def test_gap_in_extended_before_logical(self):
        # 0----10---20---30---40---50---60---70---80---90---100
        # [      p1 (extended)                                ]
        #   [      g1            ] [    p5 (logical)          ]
        info = PartitionAlignmentData(
            part_align=5,
            min_gap_size=1,
            min_start_offset=0,
            min_end_offset=0,
            ebr_space=1,
            primary_part_limit=10,
        )
        m, d = make_model_and_disk(size=100, ptable="dos")
        p1 = make_partition(m, d, offset=0, size=100, flag="extended")
        p5 = make_partition(m, d, offset=50, size=50, flag="logical")
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info), [p1, gaps.Gap(d, 5, 40, True), p5]
        )

    def test_unusable_gap_primaries(self):
        info = PartitionAlignmentData(
            part_align=10,
            min_gap_size=1,
            min_start_offset=0,
            min_end_offset=0,
            primary_part_limit=1,
        )
        m, d = make_model_and_disk(size=100)
        p = make_partition(m, d, offset=0, size=90)
        g = gaps.Gap(d, offset=90, size=10, usable=GapUsable.TOO_MANY_PRIMARY_PARTS)
        self.assertEqual(gaps.find_disk_gaps_v2(d, info), [p, g])

    def test_usable_gap_primaries(self):
        info = PartitionAlignmentData(
            part_align=10,
            min_gap_size=1,
            min_start_offset=0,
            min_end_offset=0,
            primary_part_limit=2,
        )
        m, d = make_model_and_disk(size=100)
        p = make_partition(m, d, offset=0, size=90)
        g = gaps.Gap(d, offset=90, size=10, usable=GapUsable.YES)
        self.assertEqual(gaps.find_disk_gaps_v2(d, info), [p, g])

    def test_usable_gap_extended(self):
        info = PartitionAlignmentData(
            part_align=10,
            min_gap_size=1,
            min_start_offset=0,
            min_end_offset=0,
            primary_part_limit=1,
        )
        m, d = make_model_and_disk(size=100, ptable="dos")
        p = make_partition(m, d, offset=0, size=100, flag="extended")
        g = gaps.Gap(d, offset=0, size=100, in_extended=True, usable=GapUsable.YES)
        self.assertEqual(gaps.find_disk_gaps_v2(d, info), [p, g])


class TestMovableTrailingPartitionsAndGapSize(GapTestCase):
    def test_largest_non_extended(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=10,
                min_gap_size=1,
                min_start_offset=0,
                min_end_offset=0,
                primary_part_limit=4,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # [ p1 ]         [ p2 (extended)                      ]
        #       [ g1    ][ g2                                 ]
        m, d = make_model_and_disk(size=100, ptable="dos")
        make_partition(m, d, offset=0, size=10)
        make_partition(m, d, offset=30, size=70, flag="extended")
        g = gaps.Gap(d, offset=10, size=20, in_extended=False, usable=GapUsable.YES)
        self.assertEqual(g, gaps.largest_gap(d, in_extended=False))

    def test_largest_yes_extended(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=10,
                min_gap_size=1,
                min_start_offset=0,
                min_end_offset=0,
                primary_part_limit=4,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # [ p1 ]         [ p2 (extended)                      ]
        #       [ g1    ][ g2                                 ]
        m, d = make_model_and_disk(size=100, ptable="dos")
        make_partition(m, d, offset=0, size=10)
        make_partition(m, d, offset=30, size=70, flag="extended")
        g = gaps.Gap(d, offset=30, size=70, in_extended=True, usable=GapUsable.YES)
        self.assertEqual(g, gaps.largest_gap(d, in_extended=True))

    def test_largest_any_extended(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=10,
                min_gap_size=1,
                min_start_offset=0,
                min_end_offset=0,
                primary_part_limit=4,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # [ p1 ]         [ p2 (extended)                      ]
        #       [ g1    ][ g2                                 ]
        m, d = make_model_and_disk(size=100, ptable="dos")
        make_partition(m, d, offset=0, size=10)
        make_partition(m, d, offset=30, size=70, flag="extended")
        g = gaps.Gap(d, offset=30, size=70, in_extended=True, usable=GapUsable.YES)
        self.assertEqual(g, gaps.largest_gap(d))

    def test_no_next_gap(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=10,
                min_gap_size=1,
                min_start_offset=10,
                min_end_offset=10,
                primary_part_limit=10,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1                                   ]#####
        m, d = make_model_and_disk(size=100)
        p = make_partition(m, d, offset=10, size=80)
        self.assertEqual(([], 0), gaps.movable_trailing_partitions_and_gap_size(p))

    def test_immediately_trailing_gap(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=10,
                min_gap_size=1,
                min_start_offset=10,
                min_end_offset=10,
                primary_part_limit=10,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1      ]         [ p2     ]          #####
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=10, size=20)
        p2 = make_partition(m, d, offset=50, size=20)
        self.assertEqual(([], 20), gaps.movable_trailing_partitions_and_gap_size(p1))
        self.assertEqual(([], 20), gaps.movable_trailing_partitions_and_gap_size(p2))

    def test_one_trailing_movable_partition_and_gap(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=10,
                min_gap_size=1,
                min_start_offset=10,
                min_end_offset=10,
                primary_part_limit=10,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1               ][ p2 ]              #####
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=10, size=40)
        p2 = make_partition(m, d, offset=50, size=10)
        self.assertEqual(([p2], 30), gaps.movable_trailing_partitions_and_gap_size(p1))

    def test_two_trailing_movable_partitions_and_gap(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=10,
                min_gap_size=1,
                min_start_offset=10,
                min_end_offset=10,
                primary_part_limit=10,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1               ][ p2 ][ p3 ]        #####
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=10, size=40)
        p2 = make_partition(m, d, offset=50, size=10)
        p3 = make_partition(m, d, offset=60, size=10)
        self.assertEqual(
            ([p2, p3], 20), gaps.movable_trailing_partitions_and_gap_size(p1)
        )

    def test_one_trailing_movable_partition_and_no_gap(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=10,
                min_gap_size=1,
                min_start_offset=10,
                min_end_offset=10,
                primary_part_limit=10,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1               ][ p2               ]#####
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=10, size=40)
        p2 = make_partition(m, d, offset=50, size=40)
        self.assertEqual(([p2], 0), gaps.movable_trailing_partitions_and_gap_size(p1))

    def test_full_extended_partition_then_gap(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=1,
                min_gap_size=1,
                min_start_offset=10,
                min_end_offset=10,
                primary_part_limit=10,
                ebr_space=2,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1 (extended)    ]                    #####
        # ######[ p5 (logical)    ]                    #####
        m, d = make_model_and_disk(size=100, ptable="dos")
        make_partition(m, d, offset=10, size=40, flag="extended")
        p5 = make_partition(m, d, offset=12, size=38, flag="logical")
        self.assertEqual(([], 0), gaps.movable_trailing_partitions_and_gap_size(p5))

    def test_full_extended_partition_then_part(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=1,
                min_gap_size=1,
                min_start_offset=10,
                min_end_offset=10,
                primary_part_limit=10,
                ebr_space=2,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1 (extended)    ][ p2               ]#####
        # ######[ p5 (logical)    ]                    #####
        m, d = make_model_and_disk(size=100, ptable="dos")
        make_partition(m, d, offset=10, size=40, flag="extended")
        make_partition(m, d, offset=50, size=40)
        p5 = make_partition(m, d, offset=12, size=38, flag="logical")
        self.assertEqual(([], 0), gaps.movable_trailing_partitions_and_gap_size(p5))

    def test_gap_in_extended_partition(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=1,
                min_gap_size=1,
                min_start_offset=10,
                min_end_offset=10,
                primary_part_limit=10,
                ebr_space=2,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1 (extended)    ]                    #####
        # ######[ p5 (logical)]                        #####
        m, d = make_model_and_disk(size=100, ptable="dos")
        make_partition(m, d, offset=10, size=40, flag="extended")
        p5 = make_partition(m, d, offset=12, size=30, flag="logical")
        self.assertEqual(([], 6), gaps.movable_trailing_partitions_and_gap_size(p5))

    def test_trailing_logical_partition_then_gap(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=1,
                min_gap_size=1,
                min_start_offset=10,
                min_end_offset=10,
                primary_part_limit=10,
                ebr_space=2,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1 (extended)                        ]#####
        # ######[ p5 (logical)] [ p6 (logical)]        #####
        m, d = make_model_and_disk(size=100, ptable="dos")
        make_partition(m, d, offset=10, size=80, flag="extended")
        p5 = make_partition(m, d, offset=12, size=30, flag="logical")
        p6 = make_partition(m, d, offset=44, size=30, flag="logical")
        self.assertEqual(([p6], 14), gaps.movable_trailing_partitions_and_gap_size(p5))

    def test_trailing_logical_partition_then_no_gap(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=1,
                min_gap_size=1,
                min_start_offset=10,
                min_end_offset=10,
                primary_part_limit=10,
                ebr_space=2,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1 (extended)                        ]#####
        # ######[ p5 (logical)] [ p6 (logical)       ] #####
        m, d = make_model_and_disk(size=100, ptable="dos")
        make_partition(m, d, offset=10, size=80, flag="extended")
        p5 = make_partition(m, d, offset=12, size=30, flag="logical")
        p6 = make_partition(m, d, offset=44, size=44, flag="logical")
        self.assertEqual(([p6], 0), gaps.movable_trailing_partitions_and_gap_size(p5))

    def test_trailing_preserved_partition(self):
        self.use_alignment_data(
            PartitionAlignmentData(
                part_align=10,
                min_gap_size=1,
                min_start_offset=10,
                min_end_offset=10,
                primary_part_limit=10,
            )
        )
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1               ][ p2 p   ]          #####
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=10, size=40)
        make_partition(m, d, offset=50, size=20, preserve=True)
        self.assertEqual(([], 0), gaps.movable_trailing_partitions_and_gap_size(p1))

    def test_trailing_lvm_logical_volume_no_gap(self):
        model, lv = make_model_and_lv()
        self.assertEqual(([], 0), gaps.movable_trailing_partitions_and_gap_size(lv))

    def test_trailing_lvm_logical_volume_with_gap(self):
        model, disk = make_model_and_disk(size=100 * LVM_CHUNK_SIZE + LVM_OVERHEAD)
        vg = make_vg(model, pvs={disk})
        lv = make_lv(model, vg=vg, size=40 * LVM_CHUNK_SIZE)
        self.assertEqual(
            ([], LVM_CHUNK_SIZE * 60), gaps.movable_trailing_partitions_and_gap_size(lv)
        )


class TestLargestGaps(unittest.TestCase):
    def test_basic(self):
        d = make_disk()
        [gap] = gaps.parts_and_gaps(d)
        self.assertEqual(gap, gaps.largest_gap(d))
        self.assertTrue(gap.is_usable)

    def test_two_gaps(self):
        m, d = make_model_and_disk(size=100 << 20)
        m.storage_version = 2
        make_partition(m, d, offset=0, size=20 << 20)
        make_partition(m, d, offset=40 << 20, size=20 << 20)
        [_, g1, _, g2] = gaps.parts_and_gaps(d)
        self.assertEqual(g2, gaps.largest_gap(d))
        self.assertTrue(g1.is_usable)
        self.assertTrue(g2.is_usable)

    def test_two_disks(self):
        m = make_model()
        m.storage_version = 2
        d1 = make_disk(m, size=100 << 20)
        d2 = make_disk(m, size=200 << 20)
        [d1g1] = gaps.parts_and_gaps(d1)
        [d2g1] = gaps.parts_and_gaps(d2)
        self.assertEqual(d1g1, gaps.largest_gap(d1))
        self.assertEqual(d2g1, gaps.largest_gap(d2))
        self.assertTrue(d1g1.is_usable)
        self.assertTrue(d2g1.is_usable)

    def test_across_two_disks(self):
        m = make_model()
        m.storage_version = 2
        d1 = make_disk(m, size=100 << 20)
        d2 = make_disk(m, size=200 << 20)
        [d2g1] = gaps.parts_and_gaps(d2)
        self.assertEqual(d2g1, gaps.largest_gap([d1, d2]))

    def test_across_two_disks_one_gap(self):
        m = make_model()
        m.storage_version = 2
        d1 = make_disk(m, size=100 << 20)
        d2 = make_disk(m, size=200 << 20)
        make_partition(m, d2, offset=0, size=200 << 20)
        [d1g1] = gaps.parts_and_gaps(d1)
        self.assertEqual(d1g1, gaps.largest_gap([d1, d2]))

    def test_across_two_disks_no_gaps(self):
        m = make_model()
        m.storage_version = 2
        d1 = make_disk(m, size=100 << 20)
        d2 = make_disk(m, size=200 << 20)
        make_partition(m, d1, offset=0, size=100 << 20)
        make_partition(m, d2, offset=0, size=200 << 20)
        self.assertIsNone(gaps.largest_gap([d1, d2]))


class TestUsable(unittest.TestCase):
    def test_strings(self):
        self.assertEqual("YES", GapUsable.YES.name)
        self.assertEqual(
            "TOO_MANY_PRIMARY_PARTS", GapUsable.TOO_MANY_PRIMARY_PARTS.name
        )
