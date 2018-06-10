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

from collections import defaultdict
import logging

from subiquitycore.ui.actionmenu import ActionMenu
from subiquitycore.ui.container import Columns, Pile


import attr

import urwid


log = logging.getLogger('subiquitycore.ui.table')


@attr.s
class ColSpec:
    always_scales = attr.ib(default=False)
    can_scale = attr.ib(default=False)
    omittable = attr.ib(default=False)
    min_width = attr.ib(default=0)


def demarkup(s):
    if isinstance(s, str):
        return s
    if isinstance(s, tuple):
        return demarkup(s[1])
    if isinstance(s, list):
        return [demarkup(x) for x in s]


def widget_width(w):
    if hasattr(w, 'natural_width'):
        return w.natural_width()
    elif isinstance(w, urwid.CheckBox):
        return widget_width(w._wrapped_widget)
    elif isinstance(w, (ActionMenu, urwid.AttrMap)):
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


class TableRow(urwid.WidgetWrap):

    def __init__(self, cells):
        self.cells = []
        cols = []
        for cell in cells:
            colspan = 1
            if isinstance(cell, tuple):
                colspan, cell = cell
            self.cells.append((colspan, cell))
            cols.append(cell)
        self.cells = cells
        self.columns = Columns(cols)
        super().__init__(self.columns)

    def get_natural_widths(self, always_scales):
        i = 0
        widths = {}
        for c in self.cells:
            colspan = 1
            if isinstance(c, tuple):
                colspan, c = c
            if colspan == 1 and i not in always_scales:
                widths[i] = widget_width(c)
            i += colspan
        return widths

    def set_widths(self, widths, omits, spacing):
        cols = []
        i = 0
        for c in self.cells:
            colspan = 1
            if isinstance(c, tuple):
                colspan, c = c
            assert colspan > 0
            if i not in omits:
                try:
                    w = (sum(widths[j] for j in range(i, i+colspan)) +
                         spacing*(colspan-1))
                except KeyError:
                    cols.append((c, self.columns.options('weight', 1)))
                else:
                    if w > 0:
                        cols.append((c, self.columns.options('given', w)))
            i += colspan
        self.columns.contents[:] = cols
        self.columns.dividechars = spacing


def default_container_maker(rows):
    return Pile([('pack', r) for r in rows])


class Table(urwid.WidgetWrap):

    def _select_first_selectable(self):
        self._w._select_first_selectable()

    def _select_last_selectable(self):
        self._w._select_last_selectable()

    def __init__(self, rows, colspecs=None, spacing=1,
                 container_maker=default_container_maker):
        rows = [urwid.Padding(row) for row in rows]
        self.table_rows = rows
        if colspecs is None:
            colspecs = {}
        self.colspecs = defaultdict(ColSpec, colspecs)
        self.spacing = spacing
        self._last_size = None
        self.container_maker = container_maker
        super().__init__(container_maker(rows))

    def _total_width(self, widths):
        return sum(widths.values()) + (len(list(widths.keys()))-1)*self.spacing

    def _compute_widths_for_size(self, size):
        if self._last_size == size:
            return
        always_scales = set()
        for i, cs in enumerate(self.colspecs.values()):
            if cs.always_scales:
                always_scales.add(i)
        widths = {i:cs.min_width for i, cs in self.colspecs.items()}
        for row in self.table_rows:
            row_widths = row.base_widget.get_natural_widths(always_scales)
            for i, w in row_widths.items():
                widths[i] = max(w, widths.get(i, 0))
        log.debug("%s %s %s", size[0], widths, self._total_width(widths))
        omits = set()
        if self._total_width(widths) > size[0]:
            for i in list(widths):
                if self.colspecs[i].can_scale:
                    del widths[i]
                    if self.colspecs[i].min_width:
                        while True:
                            remaining = size[0] - self._total_width(widths)
                            log.debug("remaining %s", remaining)
                            if remaining >= (self.colspecs[i].min_width
                                             + self.spacing):
                                break
                            for j in list(widths):
                                if self.colspecs[j].omittable:
                                    omits.add(j)
                                    del widths[j]
                                    break
                            else:
                                break
            total_width = size[0]
        else:
            total_width = self._total_width(widths)
        log.debug("widths %s omits %s", sorted(widths.items()), omits)
        for row in self.table_rows:
            row.width = total_width
            row.base_widget.set_widths(widths, omits, self.spacing)

    def rows(self, size, focus):
        self._compute_widths_for_size(size)
        return super().rows(size, focus)

    def render(self, size, focus):
        self._compute_widths_for_size(size)
        return super().render(size, focus)

    def set_contents(self, rows):
        self._last_size = None
        rows = [urwid.Padding(row) for row in rows]
        self.table_rows = rows
        self._w.contents[:] = self.container_maker(rows).contents


if __name__ == '__main__':
    import urwid
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
            1: ColSpec(can_scale=True, min_width=10),
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
