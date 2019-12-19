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

"""Custom overlay that only takes the space it needs but can still scroll.

There are a couple of dialogs in subiquity that basically have the form:

 +------ dialog title --------+
 |                            |
 | potentially quite long     |
 | block of text that might   |
 | take several lines and so  |
 | need to be scrollable      |
 |                            |
 |  maybe another widget      |
 |                            |
 |       [ OK     ]           |
 |       [ Cancel ]           |
 |                            |
 +----------------------------+

The way urwid works makes doing this nicely hard.  Simply putting the
text in a ListBox "works" but because the listbox is a box widget we
can't let it choose its height: either we'll end up having the text
scrollable in some situations where there is enough space on the
screen to show it all or when the screen is large there will be a
massive ugly space between the text and the following widgets.

Because you can't make a widget that behaves the way we want, this
module gives a way of providing a list of widgets to display in a Pile
and and nominating one of them to be made scrollable. A title, a list
of widgets and index to be scrollable is bundled up into an object
called a "stretchy" but is a bad name but at least easily greppable.
"""


import urwid

from subiquitycore.ui.container import ListBox, Pile


class Stretchy(metaclass=urwid.MetaSignals):

    signals = ['opened', 'closed']

    def __init__(self, title, widgets, stretchy_index, focus_index):
        """
        title: goes in the LineBox
        widgets: list of widgets to put in the pile
        stretchy_index: index into widgets of widget to wrap in ListBox
        focus_index: index into widgets of initial focus
        """
        self.title = title
        self.widgets = widgets
        self.stretchy_index = stretchy_index
        self.focus_index = focus_index

    def opened(self):
        """Called when the stretchy is placed on the screen."""
        pass

    def closed(self):
        """Called when the stretchy is removed from the screen."""

    @property
    def stretchy_w(self):
        return self.widgets[self.stretchy_index]

    def attach_context(self, context):
        urwid.connect_signal(self, 'opened', lambda: context.enter("opened"))
        urwid.connect_signal(self, 'closed', lambda: context.exit("closed"))


class StretchyOverlay(urwid.Widget):
    _selectable = True
    _sizing = frozenset([urwid.BOX])

    def __init__(self, bottom_w, stretchy):
        self.bottom_w = bottom_w
        self.stretchy = stretchy
        self.listbox = ListBox([stretchy.stretchy_w])

        def entry(i, w):
            if i == stretchy.stretchy_index:
                return ('weight', 1, self.listbox)
            else:
                return ('pack', w)

        inner_pile = Pile(
            [entry(i, w) for (i, w) in enumerate(stretchy.widgets)])
        inner_pile.focus_position = stretchy.focus_index
        # this Filler/Padding/LineBox/Filler/Padding construction
        # seems ridiculous but it works.
        self.top_w = urwid.Filler(
            urwid.Padding(
                urwid.LineBox(
                    urwid.Filler(
                        urwid.Padding(
                            inner_pile,
                            left=2, right=2),
                        top=1, bottom=1, height=('relative', 100)),
                    title=stretchy.title),
                left=3, right=3),
            top=1, bottom=1, height=('relative', 100))

    def _top_size(self, size, focus):
        # Returns the size of the top widget and whether
        # the scollbar will be shown.

        maxcol, maxrow = size  # we are a BOX widget
        outercol = min(maxcol, 80)
        # (3 outer padding, 1 line, 2 inner padding) x 2
        innercol = outercol - 12
        fixed_rows = 6  # lines at top and bottom and padding

        for i, widget in enumerate(self.stretchy.widgets):
            if i == self.stretchy.stretchy_index:
                continue
            if urwid.FLOW in widget.sizing():
                rows = widget.rows((innercol,), focus)
                fixed_rows += rows
            else:
                w_size = widget.pack((), focus)
                fixed_rows += w_size[1]

        if fixed_rows > maxrow:
            # There's no space for the stretchy widget at all,
            # probably something will break but well let's defer the
            # problem for now.
            return (outercol, size[1]), False

        stretchy_ideal_rows = self.stretchy.stretchy_w.rows((innercol,), focus)

        if maxrow - fixed_rows >= stretchy_ideal_rows:
            return (outercol, stretchy_ideal_rows + fixed_rows), False
        else:
            return (outercol, size[1]), True

    @property
    def focus(self):
        return self.top_w

    def keypress(self, size, key):
        top_size, scrollbar_visible = self._top_size(size, True)
        self.listbox.base_widget._selectable = (
            scrollbar_visible or self.stretchy.stretchy_w.selectable())
        return self.top_w.keypress(top_size, key)

    def render(self, size, focus):
        bottom_c = self.bottom_w.render(size, False)
        if not bottom_c.cols() or not bottom_c.rows():
            return urwid.CompositeCanvas(bottom_c)

        top_size, _ = self._top_size(size, focus)
        top_c = self.top_w.render(top_size, focus)
        top_c = urwid.CompositeCanvas(top_c)
        left = (size[0] - top_size[0]) // 2
        top = (size[1] - top_size[1]) // 2
        return urwid.CanvasOverlay(top_c, bottom_c, left, top)
