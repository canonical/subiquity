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
defines a Table widget that only takes up as much horizontal space as
needed for its cells. If the table want more horizontal space than is
present, there is a degree of customization available as to what to
do: you can tell which column to allow to shrink, and to omit another
column to try to keep the shrinking column above a given threshold.

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
    v = Table([
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

from subiquitycore.ui.container import Columns, Pile, WidgetWrap


import attr

import urwid


log = logging.getLogger('subiquitycore.ui.table')


@attr.s
class ColSpec:
    """Details about a column."""
    # can_shrink means that this column will be rendered narrower than
    # its natural width if there is not enough space for all columns
    # to have their natural width.
    can_shrink = attr.ib(default=False)
    # min_width is the minimum width that will be considered to be the
    # columns natural width. If the column is shrinkable it might
    # still be rendered narrower than this.
    min_width = attr.ib(default=0)
    # omittable means that this column can be omitted in an effort to
    # keep the width of a column with both can_shrink and min_width
    # set above that minimum width.
    omittable = attr.ib(default=False)


def demarkup(s):
    # Remove text markup from s.
    if isinstance(s, str):
        return s
    if isinstance(s, tuple):
        return demarkup(s[1])
    if isinstance(s, list):
        return [demarkup(x) for x in s]


def widget_width(w):
    """Return the natural width of the widget w."""
    if isinstance(w, urwid.CheckBox):
        return widget_width(w._wrapped_widget)
    elif isinstance(w, urwid.AttrMap):
        return widget_width(w._original_widget)
    elif isinstance(w, urwid.Text):
        return len(demarkup(w.text))
    elif isinstance(w, urwid.Columns):
        if len(w.contents) == 0:
            return 0
        r = 0
        for w1, o in w.contents:
            if o[0] == urwid.GIVEN:
                r += o[1]
            else:
                r += widget_width(w1)
        r += (len(w.contents) - 1) * w.dividechars
        return r
    else:
        raise Exception("don't know how to find width of %r", w)


class TableRow(WidgetWrap):
    """A row in a table.

    A wrapper around a Columns. The widths will be set when rendered.
    """

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
        self.columns = Columns(cols)
        super().__init__(self.columns)

    def _indices_cells(self):
        """Yield the column indices each cell spans and the cell.
        """
        i = 0
        for colspan, cell in self.cells:
            yield range(i, i+colspan), cell
            i += colspan

    def get_natural_widths(self):
        """Return a mapping {column-index:natural-width}.

        Cells spanning multiple columns are ignored (handled in
        adjust_for_spanning_cells).
        """
        widths = {}
        for indices, cell in self._indices_cells():
            if len(indices) == 1:
                widths[indices[0]] = widget_width(cell)
        return widths

    def adjust_for_spanning_cells(self, widths, spacing):
        """Make sure columns are wide enough for cells with colspan > 1.

        This very roughly follows the approach in
        https://www.w3.org/TR/CSS2/tables.html#width-layout.
        """
        for indices, cell in self._indices_cells():
            indices = [i for i in indices if widths[i] > 0]
            if len(indices) <= 1:
                continue
            cur_width = sum(widths[i] for i in indices) + (
                len(indices) - 1) * spacing
            cell_width = widget_width(cell)
            if cur_width < cell_width:
                # Attempt to widen each column by about the same amount.
                # But widen the first few columns by more if that's
                # whats needed.
                div, mod = divmod(cell_width - cur_width, len(indices))
                for i, j in enumerate(indices):
                    widths[j] += div + int(i <= mod)

    def set_widths(self, widths, spacing):
        """Configure row to given widths.

        `widths` is a mapping {column-index:width}. A column-index being
        missing means let the column shrink, a width being 0 means omit
        the column entirely.
        """
        cols = []
        for indices, cell in self._indices_cells():
            try:
                width = sum(widths[j] for j in indices)
            except KeyError:
                opt = self.columns.options('weight', 1)
            else:
                if width == 0:
                    continue
                width += spacing*(len(indices)-1)
                opt = self.columns.options('given', width)
            cols.append((cell, opt))
        self.columns.contents[:] = cols
        self.columns.dividechars = spacing


def _compute_widths_for_size(maxcol, table_rows, colspecs, spacing):
    """Return {column-index:width} and total width for a table."""

    def total(widths):
        ncols = sum(1 for w in widths.values() if w > 0)
        return sum(widths.values()) + (ncols-1)*spacing

    # Find the natural width for each column.
    widths = {i: cs.min_width for i, cs in colspecs.items()}
    for row in table_rows:
        row_widths = row.base_widget.get_natural_widths()
        for i, w in row_widths.items():
            widths[i] = max(w, widths.get(i, 0))

    # Make sure columns are big enough for cells that span mutiple
    # columns.
    for row in table_rows:
        row.base_widget.adjust_for_spanning_cells(widths, spacing)

    # log.debug("%s %s %s", maxcol, widths, total(widths))

    total_width = total(widths)
    # If there is not enough space, find a column that can shrink.
    #
    # If that column has a min_width, see if we need to omit any columns
    # to hit that target.
    if total(widths) > maxcol:
        for i in list(widths):
            if colspecs[i].can_shrink:
                del widths[i]
                if colspecs[i].min_width:
                    while True:
                        remaining = maxcol - total(widths)
                        if remaining >= colspecs[i].min_width + spacing:
                            break
                        for j in widths:
                            if colspecs[j].omittable:
                                widths[j] = 0
                                break
                        else:
                            break
        total_width = maxcol

    # log.debug("widths %s", sorted(widths.items()))
    return widths, total_width


def default_container_maker(rows):
    return Pile([('pack', r) for r in rows])


class Table(WidgetWrap):
    # See the module docstring for docs.

    def __init__(self, rows, colspecs=None, spacing=1,
                 container_maker=default_container_maker):
        """Create a Table.

        `rows` - a list of possibly-decorated TableRows
        `colspecs` - a mapping {column-index:ColSpec}
        'spacing` - how much space to put between cells.

        `container_maker` - something that makes a container out of a
            sequences of rows. The default packs them all into a Pile,
            the other option is to make a ListBox.
        """
        self.table_rows = [urwid.Padding(row) for row in rows]
        if colspecs is None:
            colspecs = {}
        self.colspecs = defaultdict(ColSpec, colspecs)
        self.spacing = spacing
        self.container_maker = container_maker

        super().__init__(container_maker(self.table_rows))
        self._last_size = None
        self.group = set([self])

    def bind(self, other_table):
        """Bind two tables such that they will use the same column widths.

        Don't expect anything good to happen if the two tables do not
        use the same colspecs.
        """
        self.group = other_table.group = self.group | other_table.group

    def _compute_widths_for_size(self, size):
        # Configure the table (and any bound tables) for the given size.
        if self._last_size == size:
            return
        rows = []
        for table in self.group:
            rows.extend(table.table_rows)
        widths, total_width = _compute_widths_for_size(
            size[0], rows, self.colspecs, self.spacing)
        for table in self.group:
            table._last_size = size
            for row in table.table_rows:
                row.width = total_width
                row.base_widget.set_widths(widths, self.spacing)

    def rows(self, size, focus):
        self._compute_widths_for_size(size)
        return super().rows(size, focus)

    def render(self, size, focus):
        self._compute_widths_for_size(size)
        return super().render(size, focus)

    def set_contents(self, rows):
        """Update the list of rows.

        This might not work if container_maker makes a ListBox.
        """
        self._last_size = None
        rows = [urwid.Padding(row) for row in rows]
        self.table_rows = rows
        self._w.contents[:] = self.container_maker(rows).contents


if __name__ == '__main__':
    from subiquitycore.log import setup_logger
    setup_logger('.subiquity')
    v = Table([
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
            0: ColSpec(omittable=True),
            }, spacing=4)
    v = Pile([
        ('pack', v),
        urwid.SolidFill('x'),
        ])

    def unhandled_input(*args):
        raise urwid.ExitMainLoop
    loop = urwid.MainLoop(v, unhandled_input=unhandled_input)
    loop.run()
