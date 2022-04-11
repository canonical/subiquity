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

from functools import partial
import unittest
from unittest import mock

from subiquity.models.filesystem import (
    PartitionAlignmentData,
    MiB,
    )
from subiquity.models.tests.test_filesystem import (
    make_model_and_disk,
    make_partition,
    )

from subiquity.common.filesystem import gaps


class TestGaps(unittest.TestCase):
    def test_basic(self):
        model, disk1 = make_model_and_disk()

        pg = gaps.parts_and_gaps(disk1)
        self.assertEqual(1, len(pg))
        self.assertTrue(isinstance(pg[0], gaps.Gap))
        self.assertEqual(MiB, pg[0].offset)


class TestDiskGaps(unittest.TestCase):

    def test_no_partition_gpt(self):
        size = 1 << 30
        m, d = make_model_and_disk(size=size, ptable='gpt')
        self.assertEqual(
            gaps.find_disk_gaps_v2(d),
            [gaps.Gap(d, MiB, size - 2*MiB, False)])

    def test_no_partition_dos(self):
        size = 1 << 30
        m, d = make_model_and_disk(size=size, ptable='dos')
        self.assertEqual(
            gaps.find_disk_gaps_v2(d),
            [gaps.Gap(d, MiB, size - MiB, False)])

    def test_all_partition(self):
        info = PartitionAlignmentData(
            part_align=10, min_gap_size=1, min_start_offset=0,
            min_end_offset=0, primary_part_limit=10)
        m, d = make_model_and_disk(size=100)
        p = make_partition(m, d, offset=0, size=100)
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info),
            [p])

    def test_all_partition_with_min_offsets(self):
        info = PartitionAlignmentData(
            part_align=10, min_gap_size=1, min_start_offset=10,
            min_end_offset=10, primary_part_limit=10)
        m, d = make_model_and_disk(size=100)
        p = make_partition(m, d, offset=10, size=80)
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info),
            [p])

    def test_half_partition(self):
        info = PartitionAlignmentData(
            part_align=10, min_gap_size=1, min_start_offset=0,
            min_end_offset=0, primary_part_limit=10)
        m, d = make_model_and_disk(size=100)
        p = make_partition(m, d, offset=0, size=50)
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info),
            [p, gaps.Gap(d, 50, 50)])

    def test_gap_in_middle(self):
        info = PartitionAlignmentData(
            part_align=10, min_gap_size=1, min_start_offset=0,
            min_end_offset=0, primary_part_limit=10)
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=0, size=20)
        p2 = make_partition(m, d, offset=80, size=20)
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info),
            [p1, gaps.Gap(d, 20, 60), p2])

    def test_small_gap(self):
        info = PartitionAlignmentData(
            part_align=10, min_gap_size=20, min_start_offset=0,
            min_end_offset=0, primary_part_limit=10)
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=0, size=40)
        p2 = make_partition(m, d, offset=50, size=50)
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info),
            [p1, p2])

    def test_align_gap(self):
        info = PartitionAlignmentData(
            part_align=10, min_gap_size=1, min_start_offset=0,
            min_end_offset=0, primary_part_limit=10)
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=0, size=17)
        p2 = make_partition(m, d, offset=53, size=47)
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info),
            [p1, gaps.Gap(d, 20, 30), p2])

    def test_all_extended(self):
        info = PartitionAlignmentData(
            part_align=5, min_gap_size=1, min_start_offset=0, min_end_offset=0,
            ebr_space=2, primary_part_limit=10)
        m, d = make_model_and_disk(size=100, ptable='dos')
        p = make_partition(m, d, offset=0, size=100, flag='extended')
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info),
            [
                p,
                gaps.Gap(d, 5, 95, True),
            ])

    def test_half_extended(self):
        info = PartitionAlignmentData(
            part_align=5, min_gap_size=1, min_start_offset=0, min_end_offset=0,
            ebr_space=2, primary_part_limit=10)
        m, d = make_model_and_disk(size=100)
        p = make_partition(m, d, offset=0, size=50, flag='extended')
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info),
            [p, gaps.Gap(d, 5, 45, True), gaps.Gap(d, 50, 50, False)])

    def test_half_extended_one_logical(self):
        info = PartitionAlignmentData(
            part_align=5, min_gap_size=1, min_start_offset=0, min_end_offset=0,
            ebr_space=2, primary_part_limit=10)
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=0, size=50, flag='extended')
        p2 = make_partition(m, d, offset=5, size=45, flag='logical')
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info),
            [p1, p2, gaps.Gap(d, 50, 50, False)])

    def test_half_extended_half_logical(self):
        info = PartitionAlignmentData(
            part_align=5, min_gap_size=1, min_start_offset=0, min_end_offset=0,
            ebr_space=2, primary_part_limit=10)
        m, d = make_model_and_disk(size=100, ptable='dos')
        p1 = make_partition(m, d, offset=0, size=50, flag='extended')
        p2 = make_partition(m, d, offset=5, size=25, flag='logical')
        self.assertEqual(
            gaps.find_disk_gaps_v2(d, info),
            [
                p1,
                p2,
                gaps.Gap(d, 35, 15, True),
                gaps.Gap(d, 50, 50, False),
            ])


class TestMovableTrailingPartitionsAndGapSize(unittest.TestCase):

    def use_alignment_data(self, alignment_data):
        m = mock.patch('subiquity.common.filesystem.gaps.parts_and_gaps')
        p = m.start()
        self.addCleanup(m.stop)
        p.side_effect = partial(
            gaps.find_disk_gaps_v2, info=alignment_data)

    def test_no_next_gap(self):
        self.use_alignment_data(PartitionAlignmentData(
            part_align=10, min_gap_size=1, min_start_offset=10,
            min_end_offset=10, primary_part_limit=10))
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1                                   ]#####
        m, d = make_model_and_disk(size=100)
        p = make_partition(m, d, offset=10, size=80)
        self.assertEqual(
            ([], 0),
            gaps.movable_trailing_partitions_and_gap_size(p))

    def test_immediately_trailing_gap(self):
        self.use_alignment_data(PartitionAlignmentData(
            part_align=10, min_gap_size=1, min_start_offset=10,
            min_end_offset=10, primary_part_limit=10))
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1      ]         [ p2     ]          #####
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=10, size=20)
        p2 = make_partition(m, d, offset=50, size=20)
        self.assertEqual(
            ([], 20),
            gaps.movable_trailing_partitions_and_gap_size(p1))
        self.assertEqual(
            ([], 20),
            gaps.movable_trailing_partitions_and_gap_size(p2))

    def test_one_trailing_movable_partition_and_gap(self):
        self.use_alignment_data(PartitionAlignmentData(
            part_align=10, min_gap_size=1, min_start_offset=10,
            min_end_offset=10, primary_part_limit=10))
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1               ][ p2 ]              #####
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=10, size=40)
        p2 = make_partition(m, d, offset=50, size=10)
        self.assertEqual(
            ([p2], 30),
            gaps.movable_trailing_partitions_and_gap_size(p1))

    def test_one_trailing_movable_partition_and_no_gap(self):
        self.use_alignment_data(PartitionAlignmentData(
            part_align=10, min_gap_size=1, min_start_offset=10,
            min_end_offset=10, primary_part_limit=10))
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1               ][ p2               ]#####
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=10, size=40)
        p2 = make_partition(m, d, offset=50, size=40)
        self.assertEqual(
            ([p2], 0),
            gaps.movable_trailing_partitions_and_gap_size(p1))

    def test_full_extended_partition_then_gap(self):
        self.use_alignment_data(PartitionAlignmentData(
            part_align=1, min_gap_size=1, min_start_offset=10,
            min_end_offset=10, primary_part_limit=10, ebr_space=2))
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1 (extended)    ]                    #####
        # ######[ p5 (logical)    ]                    #####
        m, d = make_model_and_disk(size=100)
        make_partition(m, d, offset=10, size=40, flag='extended')
        p5 = make_partition(m, d, offset=12, size=38, flag='logical')
        self.assertEqual(
            ([], 0),
            gaps.movable_trailing_partitions_and_gap_size(p5))

    def test_full_extended_partition_then_part(self):
        self.use_alignment_data(PartitionAlignmentData(
            part_align=1, min_gap_size=1, min_start_offset=10,
            min_end_offset=10, primary_part_limit=10, ebr_space=2))
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1 (extended)    ][ p2               ]#####
        # ######[ p5 (logical)    ]                    #####
        m, d = make_model_and_disk(size=100)
        make_partition(m, d, offset=10, size=40, flag='extended')
        make_partition(m, d, offset=50, size=40)
        p5 = make_partition(m, d, offset=12, size=38, flag='logical')
        self.assertEqual(
            ([], 0),
            gaps.movable_trailing_partitions_and_gap_size(p5))

    def test_gap_in_extended_partition(self):
        self.use_alignment_data(PartitionAlignmentData(
            part_align=1, min_gap_size=1, min_start_offset=10,
            min_end_offset=10, primary_part_limit=10, ebr_space=2))
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1 (extended)    ]                    #####
        # ######[ p5 (logical)]                        #####
        m, d = make_model_and_disk(size=100)
        make_partition(m, d, offset=10, size=40, flag='extended')
        p5 = make_partition(m, d, offset=12, size=30, flag='logical')
        self.assertEqual(
            ([], 6),
            gaps.movable_trailing_partitions_and_gap_size(p5))

    def test_trailing_logical_partition_then_gap(self):
        self.use_alignment_data(PartitionAlignmentData(
            part_align=1, min_gap_size=1, min_start_offset=10,
            min_end_offset=10, primary_part_limit=10, ebr_space=2))
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1 (extended)                        ]#####
        # ######[ p5 (logical)] [ p6 (logical)]        #####
        m, d = make_model_and_disk(size=100)
        make_partition(m, d, offset=10, size=80, flag='extended')
        p5 = make_partition(m, d, offset=12, size=30, flag='logical')
        p6 = make_partition(m, d, offset=44, size=30, flag='logical')
        self.assertEqual(
            ([p6], 14),
            gaps.movable_trailing_partitions_and_gap_size(p5))

    def test_trailing_logical_partition_then_no_gap(self):
        self.use_alignment_data(PartitionAlignmentData(
            part_align=1, min_gap_size=1, min_start_offset=10,
            min_end_offset=10, primary_part_limit=10, ebr_space=2))
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1 (extended)                        ]#####
        # ######[ p5 (logical)] [ p6 (logical)       ] #####
        m, d = make_model_and_disk(size=100)
        make_partition(m, d, offset=10, size=80, flag='extended')
        p5 = make_partition(m, d, offset=12, size=30, flag='logical')
        p6 = make_partition(m, d, offset=44, size=44, flag='logical')
        self.assertEqual(
            ([p6], 0),
            gaps.movable_trailing_partitions_and_gap_size(p5))

    def test_trailing_preserved_partition(self):
        self.use_alignment_data(PartitionAlignmentData(
            part_align=10, min_gap_size=1, min_start_offset=10,
            min_end_offset=10, primary_part_limit=10))
        # 0----10---20---30---40---50---60---70---80---90---100
        # #####[ p1               ][ p2 p   ]          #####
        m, d = make_model_and_disk(size=100)
        p1 = make_partition(m, d, offset=10, size=40)
        make_partition(m, d, offset=50, size=20, preserve=True)
        self.assertEqual(
            ([], 0),
            gaps.movable_trailing_partitions_and_gap_size(p1))
