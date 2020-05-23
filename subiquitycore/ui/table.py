# Copyright 2018 Canonical, Ltd.
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

"""
A table widget.

One of the principles of urwid is that widgets get their size from
their container rather than deciding it for themselves. At times (as
in stretchy.py) this does not make for the best UI. This module
defines TablePile and TableListBox widgets that by default only take
up as much horizontal space as needed for their cells. If the table
wants more horizontal space than is present, there is a degree of
customization available as to what to do: you can tell which column to
allow to shrink, and to omit another column to try to keep the
shrinking column above a given threshold.

You can also let columns take all available space, as is the urwid
default.

Other features include cells that span multiple columns and binding
tables together so that they use the same widths for their columns.

There is not a lot of care about how the various features interact, so
be careful, or rather do not be surprised when things break. Gotchas
that have occurred to me during implementation:

1. This code needs to know the "natural width" of anything you put
   into a table. Don't be surprised if widget_width needs extending.
2. Having a cell that spans multiple columns span a column that can
   shrink or be omitted will be confusing.
3. Binding tables together that have different column options will
   similarly not do anything sensible.
4. You can wrap table rows in decorators that do not affect their size
   (AttrMap, etc) but do not use ones that do affect size (Padding,
   etc) or things will get confusing.
5. I haven't tested this code with more than one column that can
   shrink or more than one column that can be omitted.

Example:

```
    v = TablePile([
        TableRow([
            urwid.Text("aa"),
            (2, urwid.Text("0123456789"*5, wrap='clip')),
            urwid.Text('eeee')]),
        TableRow([
            urwid.Text("ccc"),
            urwid.Text("0123456789"*4, wrap='clip'),
            urwid.Text('fff'*10), urwid.Text('g')]),
        ], {
            0: ColSpec(omittable=True),
            1: ColSpec(can_shrink=True, min_width=10),
            }, spacing=4)
```
"""

from collections import defaultdict
import logging


from subiquitycore.ui.container import (
    Columns,
    ListBox,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.width import widget_width

import attr

import urwid


log = logging.getLogger('subiquitycore.ui.table')


@attr.s
class ColSpec:
    """Details about a column."""
    # Columns with pack=True take as much space as they need. Colunms
    # with pack=False have the space remaining after pack=True columns
    # are sized allocated to them.
    pack = attr.ib(default=True)
    # can_shrink means that this column will be rendered narrower than
    # its natural width if there is not enough space for all columns
    # to have their natural width.
    can_shrink = attr.ib(default=False)
    # min_width is the minimum width that will be considered to be the
    # columns natural width. If the column is shrinkable (or
    # pack=False) it might still be rendered narrower than this.
    min_width = attr.ib(default=0)
    # omittable means that this column can be omitted in an effort to
    # keep the width of a column with min_width set above that minimum
    # width.
    omittable = attr.ib(default=False)
    # rpad is the width of padding to the right of this column. None
    # means use the table's default spacing (if not the last column in
    # the row -- that gets no padding to the right by default).
    rpad = attr.ib(default=None)


def _width(widths, user_indices):
    # widths = {underlying-index: width}
    # user_indices = iterable of user-indices
    # return the width spanned by the specified columns, including
    # internal but not external padding.
    user_indices = sorted(user_indices)
    r = sum(widths[2*i] + widths.get(2*i+1, 0) for i in user_indices[:-1])
    r += widths[2*user_indices[-1]]
    return r


class TableRow(WidgetWrap):
    """A row in a table.

    A wrapper around a Columns. The widths will be set when rendered.
    """

    # To allow for variable padding between columns, we can't use
    # Columns.dividechars. Instead, the padding is implemented as
    # extra columns. This complicates things because "column i"
    # becomes a bit ambiguous -- does it mean the i'th column from the
    # user's POV, or does it mean the i'th column in the Columns from
    # urwid's POV? This code tries to refer to the former as the "user
    # index" and the latter as the "underlying index". Mapping from
    # one to the other is pretty simple: underlying-index = 2*user-index.

    def __init__(self, cells):
        """cells is a list of [widget] or [(colspan, widget)].

        colspan is assumed to be 1 if omitted.
        """
        self.cells = []
        cols = []
        for cell in cells:
            colspan = 1
            if isinstance(cell, tuple):
                colspan, cell = cell
            assert colspan > 0
            self.cells.append((colspan, cell))
            cols.append(cell)
            cols.append(urwid.Text(""))
        del cols[-1]
        self.columns = Columns(cols)
        super().__init__(self.columns)

    def selectable(self):
        for w, _ in self._w.contents:
            if w.selectable():
                return True
        return False

    def _user_indices_cells(self):
        """Yield the user indices each cell spans and the cell.
        """
        user_i = 0
        for colspan, cell in self.cells:
            yield range(user_i, user_i+colspan), cell
            user_i += colspan

    def get_natural_widths(self, unpacked_cols):
        """Return a mapping {underlying-index:natural-width}.

        Cells spanning multiple columns are ignored (handled in
        adjust_for_spanning_cells).
        """
        widths = {}
        for user_indices, cell in self._user_indices_cells():
            if len(user_indices) == 1 and user_indices[0] not in unpacked_cols:
                widths[2*user_indices[0]] = widget_width(cell)
        return widths

    def adjust_for_spanning_cells(self, unpacked_user_indices,
                                  no_inherent_size, widths):
        """Make sure columns are wide enough for cells with colspan > 1.

        This very roughly follows the approach in
        https://www.w3.org/TR/CSS2/tables.html#width-layout.
        """
        for user_indices, cell in self._user_indices_cells():
            if set(user_indices) & unpacked_user_indices:
                continue
            if len(user_indices) <= 1:
                continue
            cur_width = _width(widths, user_indices)
            cell_width = widget_width(cell)
            if cur_width < cell_width:
                # If any of the spanned columns have no inherent size (i.e. all
                # the cells in that column also span another column), only
                # widen those columns.
                unsized = set(user_indices) & no_inherent_size
                if unsized:
                    user_indices = unsized
                # Attempt to widen each column by about the same amount.
                # But widen the first few columns by more if that's
                # whats needed.
                div, mod = divmod(cell_width - cur_width, len(user_indices))
                for i, user_j in enumerate(user_indices):
                    widths[2*user_j] += div + int(i < mod)

    def set_widths(self, widths):
        """Configure row to given widths.

        `widths` is a mapping {underlying-index:width}. An index being
        missing means let the column shrink, a width being 0 means omit
        the column entirely.
        """
        cols = []
        for user_indices, cell in self._user_indices_cells():
            try:
                width = _width(widths, user_indices)
            except KeyError:
                opt = self.columns.options('weight', 1)
            else:
                if width == 0:
                    continue
                opt = self.columns.options('given', width)
            cols.append((cell, opt))
            n = widths.get(2*max(user_indices) + 1, 0)
            if n:
                cols.append((urwid.Text(""), self.columns.options('given', n)))
        self.columns.contents[:] = cols


def _compute_widths_for_size(maxcol, table_rows, colspecs, default_spacing):
    """Return {cell-index:width} and total width for a table."""

    unpacked_user_indices = {
        user_i for user_i, cs in colspecs.items() if not cs.pack}

    # Find the natural width for each column.
    # widths maps underyling index to width
    widths = {2*i: cs.min_width for i, cs in colspecs.items() if cs.pack}
    for row in table_rows:
        row_widths = row.base_widget.get_natural_widths(unpacked_user_indices)
        for underlying_i, w in row_widths.items():
            widths[underlying_i] = max(w, widths.get(underlying_i, 0))

    # count the columns...
    colcount = max(widths.keys())//2 + 1
    if unpacked_user_indices:
        colcount = max(colcount, max(unpacked_user_indices) + 1)

    no_inherent_size = set()
    for user_i in range(colcount):
        if user_i not in unpacked_user_indices \
          and widths.get(2*user_i, 0) == 0:
            no_inherent_size.add(user_i)
            widths[2*user_i] = 0

    # Set the widths of the spacing columns.
    widths.update(
        {2*user_i+1: default_spacing for user_i in range(colcount-1)})
    widths.update(
        {2*user_i+1: cs.rpad for user_i, cs in colspecs.items()
         if cs.rpad is not None})

    widths_before = widths.copy()

    # Make sure columns are big enough for cells that span mutiple
    # columns.
    for row in table_rows:
        row.base_widget.adjust_for_spanning_cells(
            unpacked_user_indices, no_inherent_size, widths)

    # log.debug("%s", (maxcol, widths.items(),
    #                  sum(widths.values()), unpacked_user_indices))

    total_width = sum(widths.values())
    # If there is not enough space, find a column that can shrink.
    #
    # If that column has a min_width, see if we need to omit any columns
    # to hit that target.
    if total_width > maxcol or unpacked_user_indices:

        for user_i in range(colcount):
            if not colspecs[user_i].can_shrink and 2*user_i in widths:
                widths[2*user_i] = widths_before[2*user_i]

        for user_i in range(colcount):
            if colspecs[user_i].can_shrink or not colspecs[user_i].pack:
                if 2*user_i in widths:
                    del widths[2*user_i]
                if colspecs[user_i].min_width:
                    while True:
                        remaining = maxcol - sum(widths.values())
                        if remaining >= colspecs[user_i].min_width:
                            break
                        for user_j in range(colcount):
                            if not colspecs[user_j].omittable:
                                continue
                            if widths.get(2*user_j):
                                widths[2*user_j] = 0
                                widths[2*user_j+1] = 0
                                break
                        else:
                            break
        total_width = maxcol

    # log.debug("widths %s", sorted(widths.items()))
    return widths, total_width, bool(unpacked_user_indices)


class AbstractTable(WidgetWrap):
    # See the module docstring for docs.

    def __init__(self, rows, colspecs=None, spacing=1, align='left'):
        """Create a Table.

        `rows` - a list of possibly-decorated TableRows
        `colspecs` - a mapping {column-index:ColSpec}
        'spacing` - how much space to put between cells.
        """
        self.table_rows = [urwid.Padding(row, align=align) for row in rows]
        if colspecs is None:
            colspecs = {}
        self.colspecs = defaultdict(ColSpec, colspecs)
        self.spacing = spacing

        super().__init__(self._make(self.table_rows))
        self._last_size = None
        self.group = set([self])

    def bind(self, other_table):
        """Bind two tables such that they will use the same column widths.

        Don't expect anything good to happen if the two tables do not
        use the same colspecs.
        """
        new_group = self.group | other_table.group
        for table in new_group:
            table.group = new_group

    def invalidate(self):
        self._last_size = None

    def _compute_widths_for_size(self, size):
        # Configure the table (and any bound tables) for the given size.
        if self._last_size == size:
            return
        rows = []
        for table in self.group:
            rows.extend(table.table_rows)
        widths, total_width, has_unpacked = _compute_widths_for_size(
            size[0], rows, self.colspecs, self.spacing)
        for table in self.group:
            table._last_size = size
            for row in table.table_rows:
                if not has_unpacked:
                    row.width = total_width
                row.base_widget.set_widths(widths)

    def get_natural_width(self):
        rows = []
        for table in self.group:
            rows.extend(table.table_rows)
        widths, total_width, has_unpacked = _compute_widths_for_size(
            100000, rows, self.colspecs, self.spacing)
        return total_width

    def rows(self, size, focus):
        self._compute_widths_for_size(size)
        return super().rows(size, focus)

    def render(self, size, focus):
        self._compute_widths_for_size(size)
        return super().render(size, focus)

    @property
    def focus_position(self):
        return self._w.base_widget.focus_position

    @focus_position.setter
    def focus_position(self, val):
        self._w.base_widget.focus_position = val


class TablePile(AbstractTable):

    def _make(self, rows):
        return Pile([('pack', r) for r in rows])

    def insert_rows(self, index, new_rows):
        self.invalidate()
        self.table_rows[index:index] = new_rows
        self._w.contents[index:index] = [
            (urwid.Padding(w), self._w.options('pack')) for w in new_rows]

    def remove_rows(self, start, end):
        self.invalidate()
        # MonitoredFocusList clamps the focus position to the new
        # length of the list when you remove elements but it doesn't
        # check that that the element it moves the focus to is
        # selectable...
        new_length = len(self._w.contents) - (end - start)
        refocus = self._w.focus_position >= new_length
        del self.table_rows[start:end]
        del self._w.contents[start:end]
        if refocus:
            self._select_last_selectable()
        else:
            while not self._w.focus.selectable():
                self._w.focus_position += 1

    def set_contents(self, rows):
        """Update the list of rows. """
        self.invalidate()
        rows = [urwid.Padding(row) for row in rows]
        self.table_rows = rows
        empty_before = len(self._w.contents) == 0
        self._w.contents[:] = [(row, self._w.options('pack')) for row in rows]
        empty_after = len(self._w.contents) == 0
        # Pile / MonitoredFocusList have this strange behaviour where
        # when you add rows to an empty pile by assigning to contents,
        # the last row added ends up being the focus even if it's not
        # selectable.
        if empty_before and not empty_after:
            self._select_first_selectable()


class TableListBox(AbstractTable):

    def _make(self, rows):
        return ListBox(rows)

    def set_contents(self, rows):
        """Update the list of rows. """
        self.invalidate()
        rows = [urwid.Padding(row) for row in rows]
        self.table_rows = rows
        body = self._w.base_widget.body
        empty_before = len(body) == 0
        body[:] = rows
        empty_after = len(body) == 0
        # Pile / MonitoredFocusList have this strange behaviour where
        # when you add rows to an empty pile by assigning to contents,
        # the last row added ends up being the focus even if it's not
        # selectable.
        if empty_before and not empty_after:
            self._select_first_selectable()


if __name__ == '__main__':
    from subiquitycore.log import setup_logger
    setup_logger('.subiquity')
    v = TablePile([
        TableRow([
            urwid.Text("aa"),
            (2, urwid.Text("0123456789"*5, wrap='clip')),
            urwid.Text('eeee')]),
        TableRow([
            urwid.Text("ccc"),
            urwid.Text("0123456789"*4, wrap='clip'),
            urwid.Text('fff'*10), urwid.Text('g')]),
        ], {
            1: ColSpec(can_shrink=True, min_width=10),
            0: ColSpec(omittable=True, rpad=1),
            }, spacing=4)
    v = Pile([
        ('pack', v),
        urwid.SolidFill('x'),
        ])

    def unhandled_input(*args):
        raise urwid.ExitMainLoop
    loop = urwid.MainLoop(v, unhandled_input=unhandled_input)
    loop.run()
