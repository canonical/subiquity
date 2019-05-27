# Copyright 2019 Canonical, Ltd.
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

from collections import defaultdict
from unittest import TestCase

from urwid import Text

from subiquitycore.ui.table import (
    _compute_widths_for_size,
    ColSpec,
    TableRow,
    )


class TestComputeWidthsForSize(TestCase):

    def rowsForContentSizes(self, sizes):
        rows = []
        for row in sizes:
            cells = []
            for size in row:
                if not isinstance(size, tuple):
                    span = 1
                else:
                    span, size = size
                cells.append((span, Text("x"*size)))
            rows.append(TableRow(cells))
        return rows

    def test_simple(self):
        trows = self.rowsForContentSizes([[10]])
        widths, total, has_unpacked = _compute_widths_for_size(
            100, trows, defaultdict(ColSpec, {}), 0)
        self.assertEqual(
            ({0: 10}, 10, False),
            (widths, total, has_unpacked),
            )

    def test_two_cols(self):
        trows = self.rowsForContentSizes([[10, 10]])
        widths, total, has_unpacked = _compute_widths_for_size(
            100, trows, defaultdict(ColSpec, {}), 0)
        self.assertEqual(
            ({0: 10, 1: 0, 2: 10}, 20, False),
            (widths, total, has_unpacked),
            )

    def test_two_cols_confined(self):
        # When there is not enough space for the table, a column with
        # can_shrink=True is not assigned a width so urwid can give
        # that column as much space as it can.
        trows = self.rowsForContentSizes([[10, 10]])
        colspecs = defaultdict(
            ColSpec, {0: ColSpec(can_shrink=True)})
        widths, total, has_unpacked = _compute_widths_for_size(
            15, trows, colspecs, 0)
        self.assertEqual(
            ({1: 0, 2: 10}, 15, False),
            (widths, total, has_unpacked),
            )

    def test_two_cols_spacing(self):
        trows = self.rowsForContentSizes([[10, 10]])
        widths, total, has_unpacked = _compute_widths_for_size(
            100, trows, defaultdict(ColSpec, {}), 2)
        self.assertEqual(
            ({0: 10, 1: 2, 2: 10}, 22, False),
            (widths, total, has_unpacked),
            )

    def test_three_cols_spacing_rpad(self):
        # rpad overrides the spacing to the right of a column
        trows = self.rowsForContentSizes([[10, 10, 10]])
        colspecs = defaultdict(
            ColSpec, {0: ColSpec(rpad=40)})
        widths, total, has_unpacked = _compute_widths_for_size(
            100, trows, colspecs, 2)
        self.assertEqual(
            ({0: 10, 1: 40, 2: 10, 3: 2, 4: 10}, 72, False),
            (widths, total, has_unpacked),
            )

    def test_no_inherent_width(self):
        # If a column has no cells that span only that column, it gets
        # allocated space in preference to other columns.  Content
        # like this:
        #
        #    [[(2, "longer content567890"), "shorter890"],
        #     ["shorter890", (2, "longer content5")]]
        #
        # should be rendered like this:
        #
        #    +----------------------+------------+
        #    | longer content567890 | shorter890 |
        #    +------------+---------+------------+
        #    | shorter890 | longer content5      |
        #    +------------+----------------------+
        trows = self.rowsForContentSizes([[(2, 20), 10],
                                          [10, (2, 15)]])
        widths, total, has_unpacked = _compute_widths_for_size(
            100, trows, defaultdict(ColSpec, {}), 0)
        self.assertEqual(
            ({0: 10, 1: 0, 2: 10, 3: 0, 4: 10}, 30, False),
            (widths, total, has_unpacked),
            )

    def test_no_inherent_width_confined(self):
        #    [[(2, "longer content567890"), "shorter890"],
        #     ["shorter890", (2, "longer content5")]]
        #
        # should be rendered like this if the view is not quite wide
        # enough (and column 1 has can_shrink=True):
        #
        #    +--------------------+------------+
        #    | longer content5678 | shorter890 |
        #    | 90                 |            |
        #    +------------+-------+------------+
        #    | shorter890 | longer content5    |
        #    +------------+--------------------+
        #
        # This is represented by column 1 not being assigned a width
        # at all, so urwid gives it as much space as it can.
        trows = self.rowsForContentSizes([[(2, 20), 10],
                                          [10, (2, 15)]])
        colspecs = defaultdict(
            ColSpec, {1: ColSpec(can_shrink=True)})
        widths, total, has_unpacked = _compute_widths_for_size(
            28, trows, colspecs, 0)
        self.assertEqual(
            ({0: 10, 1: 0, 3: 0, 4: 10}, 28, False),
            (widths, total, has_unpacked),
            )
