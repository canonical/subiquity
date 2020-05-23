# Copyright 2015 Canonical, Ltd.
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

""" UI utilities """

from functools import partialmethod
import logging

from urwid import (
    ACTIVATE,
    AttrMap,
    CompositeCanvas,
    connect_signal,
    Padding as _Padding,
    SelectableIcon,
    Text,
    WidgetDecoration,
    WidgetDisable,
    )

from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.container import ListBox, Pile
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import TableRow
from subiquitycore.ui.width import widget_width


log = logging.getLogger("subiquitycore.ui.utils")


def apply_padders(cls):
    """ Decorator for generating useful padding methods

    Loops through and generates methods like:

      Padding.push_1(Widget)

      Sets the left padding attribute by 1

      Padding.pull_24(Widget)

      Sets right padding attribute by 24.

      Padding.center_50(Widget)

      Provides center padding with a relative width of 50
    """
    padding_count = 100

    for i in range(1, padding_count):
        setattr(cls, 'push_{}'.format(i), partialmethod(_Padding, left=i))
        setattr(cls, 'pull_{}'.format(i), partialmethod(_Padding, right=i))
        setattr(cls, 'fixed_{}'.format(i),
                partialmethod(_Padding, align='center',
                              width=i, min_width=i))
        setattr(cls, 'center_{}'.format(i),
                partialmethod(_Padding, align='center',
                              width=('relative', i)))
        setattr(cls, 'left_{}'.format(i),
                partialmethod(_Padding, align='left',
                              width=('relative', i)))
        setattr(cls, 'right_{}'.format(i),
                partialmethod(_Padding, align='right',
                              width=('relative', i)))
    return cls


@apply_padders
class Padding:
    """ Padding methods

    .. py:meth:: push_X(:class:`urwid.Widget`)

       This method supports padding the left side of the widget
       from 1-99, for example:

       .. code::

          Padding.push_20(Text("This will be indented 20 columns")

    .. py:meth:: pull_X(:class:`urwid.Widget`)

       This method supports padding the right side of the widget
       from 1-99, for example:

       .. code::

          Padding.pull_20(Text("This will be right indented 20 columns")

    .. py:meth:: fixed_X(:class:`urwid.Widget`)

       This method supports padding the widget to a fixed size and
       centering it.
       from 1-99, for example:

       .. code::

          Padding.fixed_20(Text("This will be centered and fixed sized
                                 of 20 columns"))

    .. py:meth:: center_X(:class:`urwid.Widget`)

       This method centers a widget with X being the relative width of
       the widget.

       .. code::

          Padding.center_10(Text("This will be centered with a "
                                 "width of 10 columns"))

    .. py:meth:: left_X(:class:`urwid.Widget`)

       This method aligns a widget left with X being the relative width of
       the widget.

       .. code::

          Padding.left_10(Text("This will be left aligned with a "
                               "width of 10 columns"))

    .. py:meth:: right_X(:class:`urwid.Widget`)

       This method right aligns a widget with X being the relative width of
       the widget.

       .. code::

          Padding.right_10(Text("This will be right aligned with a "
                                "width of 10 columns"))

    """
    line_break = partialmethod(Text)


# This makes assumptions about the style names defined by both
# subiquity and console_conf. The fix is to stop using the Color class
# below, I think.
STYLE_NAMES = set([
    'body',
    'danger_button focus',
    'danger_button',
    'done_button focus',
    'done_button',
    'frame_button focus',
    'frame_button',
    'frame_header',
    'frame_header_fringe',
    'info_error',
    'info_minor',
    'info_primary',
    'menu_button focus',
    'menu_button',
    'other_button focus',
    'other_button',
    'progress_complete',
    'progress_incomplete',
    'scrollbar focus',
    'scrollbar',
    'string_input focus',
    'string_input',
])


def apply_style_map(cls):
    """ Applies AttrMap attributes to Color class

    Eg:

      Color.frame_header(Text("I'm text in the Orange frame header"))
      Color.body(Text("Im text in wrapped with the body color"))
    """
    for k in STYLE_NAMES:
        kf = k + ' focus'
        if kf in STYLE_NAMES:
            setattr(cls, k, partialmethod(AttrMap, attr_map=k, focus_map=kf))
        else:
            setattr(cls, k, partialmethod(AttrMap, attr_map=k))
    return cls


@apply_style_map
class Color:
    """ Partial methods for :class:`~subiquity.palette.STYLES`

    .. py:meth:: frame_header(:class:`urwid.Widget`)

       This method colors widget based on the style map used.

       .. code::

          Color.frame_header(Text("This will use foreground and background "
                                  "defined from the STYLES attribute"))

    """
    pass


_disable_everything_map = {k: 'info_minor' for k in STYLE_NAMES | set([None])}


def disabled(w):
    return WidgetDisable(AttrMap(w, _disable_everything_map))


def undisabled(w):
    if isinstance(w, WidgetDisable):
        w = w.original_widget
    if isinstance(w, AttrMap):
        w = w.original_widget
    return w


def button_pile(buttons):
    width = 14
    for button in buttons:
        width = max(widget_width(button), width)
    return _Padding(
        Pile(buttons), min_width=width, width=width, align='center')


def screen(rows, buttons=None, focus_buttons=True, excerpt=None,
           narrow_rows=False):
    """Helper to create a common screen layout.

    The commonest screen layout in subiquity is:

        [ 1 line padding (optional) ]
        excerpt (optional)
        [ 1 line padding ]
        Box widget (usually a ListBox)
        [ 1 line padding ]
        a button_pile
        [ 1 line padding ]

    This helper makes creating this a 1-liner.
    """
    if isinstance(rows, list):
        rows = ListBox(rows)
    if narrow_rows:
        rows = Padding.center_63(rows)
    if buttons is None:
        focus_buttons = False
    elif isinstance(buttons, list):
        buttons = button_pile(buttons)
    excerpt_rows = []
    if excerpt is not None:
        excerpt_rows = [
            ('pack', Text(excerpt)),
            ('pack', Text("")),
            ]
    body = [
        rows,
        ('pack', Text("")),
    ]
    if buttons is not None:
        body.extend([
            ('pack', buttons),
            ('pack', Text("")),
        ])
    pile = Pile(excerpt_rows + body)
    if focus_buttons:
        pile.focus_position = len(excerpt_rows) + 2
    return Padding.center_79(pile, min_width=76)


class CursorOverride(WidgetDecoration):
    """Decoration to override where the cursor goes when a widget is focused.
    """

    has_original_width = True

    def __init__(self, w, cursor_x=0):
        super().__init__(w)
        self.cursor_x = cursor_x

    def get_cursor_coords(self, size):
        return self.cursor_x, 0

    def rows(self, size, focus):
        return self._original_widget.rows(size, focus)

    def keypress(self, size, focus):
        return self._original_widget.keypress(size, focus)

    def render(self, size, focus=False):
        c = self._original_widget.render(size, focus)
        if focus:
            # create a new canvas so we can add a cursor
            c = CompositeCanvas(c)
            c.cursor = self.get_cursor_coords(size)
        return c


class ClickableIcon(SelectableIcon):
    """Like Button, but simpler. """
    signals = ['click']

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        self._emit('click')


def make_action_menu_row(
        cells,
        menu,
        attr_map='menu_button', focus_map='menu_button focus',
        cursor_x=2):
    row = TableRow(cells)
    if not isinstance(attr_map, dict):
        attr_map = {None: attr_map}
    if not isinstance(focus_map, dict):
        focus_map = {None: focus_map}
    am = AttrMap(CursorOverride(row, cursor_x=cursor_x), attr_map, focus_map)
    connect_signal(menu, 'open', lambda menu: am.set_attr_map(focus_map))
    connect_signal(menu, 'close', lambda menu: am.set_attr_map(attr_map))
    return am


def rewrap(text):
    paras = text.split("\n\n")
    return "\n\n".join([p.replace('\n', ' ') for p in paras]).strip()


class SomethingFailed(Stretchy):
    def __init__(self, parent, msg, stderr):
        self.parent = parent
        ok = other_btn(label=_("Close"), on_press=self.close)
        widgets = [
            Text(msg),
            Text(""),
            Text(stderr.strip('\n')),
            Text(""),
            button_pile([ok]),
            ]
        super().__init__(
            "",
            widgets,
            2, 4)

    def close(self, sender):
        self.parent.remove_overlay()
