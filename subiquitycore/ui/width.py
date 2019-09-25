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

import urwid


size_neutral_decorations = (
    urwid.AttrMap,
    urwid.PopUpLauncher,
    urwid.WidgetDisable,
    )

size_neutral_widget_wraps = (
    urwid.Button,
    urwid.CheckBox,
    )


def widget_width(w):
    """Return the natural width of the widget w."""
    if (isinstance(w, urwid.WidgetDecoration)
            and getattr(w, 'has_original_width', False)):
        return widget_width(w.original_widget)
    if hasattr(w, 'get_natural_width'):
        return w.get_natural_width()
    if isinstance(w, size_neutral_widget_wraps):
        return widget_width(w._wrapped_widget)
    if isinstance(w, size_neutral_decorations):
        return widget_width(w.original_widget)
    if isinstance(w, urwid.Padding):
        if w.width == urwid.RELATIVE_100:
            return w.left + w.right + widget_width(w.original_widget)
        elif isinstance(w.width, int):
            return w.width
    if isinstance(w, urwid.Text):
        return len(w.text)
    if isinstance(w, urwid.Columns):
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
    raise Exception("don't know how to find width of %r", w)
