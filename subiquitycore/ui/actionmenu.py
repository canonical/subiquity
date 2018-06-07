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

from urwid import (
    ACTIVATE,
    AttrWrap,
    Button,
    CompositeCanvas,
    connect_signal,
    LineBox,
    PopUpLauncher,
    Text,
    WidgetWrap,
    Widget,
    )

from subiquitycore.ui.container import Columns, ListBox
from subiquitycore.ui.selector import Option
from subiquitycore.ui.utils import Color


class ActionBackButton(Button):
    button_left = Text("<")
    button_right = Text("")


class ActionMenuButton(Button):
    button_left = Text("")
    button_right = Text(">")


class _ActionMenuDialog(WidgetWrap):
    """A list of action buttons with a box around them."""

    def __init__(self, parent):
        self.parent = parent
        close = ActionBackButton("(close)")
        connect_signal(close, "click", self.close)
        group = [Color.menu_button(close)]
        width = 0
        for i, option in enumerate(self.parent._options):
            if option.enabled:
                if isinstance(option.label, Widget):
                    btn = option.label
                else:
                    btn = Color.menu_button(ActionMenuButton(option.label))
                width = max(width, len(btn.base_widget.label))
                connect_signal(
                    btn.base_widget, 'click', self.click, option.value)
            else:
                label = option.label
                if isinstance(label, Widget):
                    label = label.base_widget.label
                width = max(width, len(label))
                btn = Columns([
                    ('fixed', 1, Text("")),
                    Text(label),
                    ('fixed', 1, Text(">")),
                    ], dividechars=1)
                btn = AttrWrap(btn, 'info_minor')
            group.append(btn)
        self.width = width
        self.lb = ListBox(group)
        super().__init__(LineBox(self.lb))

    def close(self, sender=None):
        self.parent._button.close_pop_up()

    def click(self, btn, value):
        self.parent._action(value)
        self.close()

    def keypress(self, size, key):
        if key == 'esc':
            self.close()
        else:
            return super().keypress(size, key)


class _ActionMenuLauncher(PopUpLauncher):
    def __init__(self, parent):
        self.parent = parent
        super().__init__(Text(">"))

    def open_pop_up(self):
        self.parent.attr_map.set_attr_map({None: 'menu_button focus'})
        super().open_pop_up()

    def close_pop_up(self):
        self.parent.attr_map.set_attr_map({None: 'menu_button'})
        super().close_pop_up()

    def create_pop_up(self):
        self.parent._dialog.lb.base_widget.focus_position = 0
        return self.parent._dialog

    def get_pop_up_parameters(self):
        width = self.parent._dialog.width + 7
        return {
            'left': 1,
            'top': -1,
            'overlay_width': width,
            'overlay_height': len(self.parent._options) + 3,
            }


class ActionMenu(WidgetWrap):

    signals = ['action']

    def __init__(self, content_width, content, opts):
        self._options = []
        for opt in opts:
            if not isinstance(opt, Option):
                opt = Option(opt)
            self._options.append(opt)
        self._button = _ActionMenuLauncher(self)
        c1 = Columns([(1, Text("")), (content_width, content), (1, self._button)], 1)
        self.attr_map = Color.menu_button(c1)
        c2 = Columns([(content_width+4, self.attr_map), Text("")])
        super().__init__(c2)
        self._dialog = _ActionMenuDialog(self)

    def get_cursor_coords(self, size):
        return 2,0

    def render(self, size, focus):
        c = super().render(size, focus)
        if focus:
            # create a new canvas so we can add a cursor
            c = CompositeCanvas(c)
            c.cursor = self.get_cursor_coords(size)
        return c

    def selectable(self):
        return True

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        self._button.open_pop_up()

    def _action(self, action):
        self._emit("action", action)

