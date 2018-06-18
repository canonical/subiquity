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
    connect_signal,
    LineBox,
    PopUpLauncher,
    SelectableIcon,
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
        super().__init__(LineBox(ListBox(group)))

    def close(self, sender):
        self.parent.close_pop_up()

    def click(self, btn, value):
        self.parent._action(value)
        self.parent.close_pop_up()

    def keypress(self, size, key):
        if key == 'esc':
            self.parent.close_pop_up()
        else:
            return super().keypress(size, key)


class ActionMenu(PopUpLauncher):

    icon = ">"

    signals = ['action', 'open', 'close']

    def __init__(self, opts):
        self._options = []
        for opt in opts:
            if not isinstance(opt, Option):
                opt = Option(opt)
            self._options.append(opt)
        self._button = SelectableIcon(self.icon, 0)
        super().__init__(self._button)
        self._dialog = _ActionMenuDialog(self)

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        self.open_pop_up()

    def _action(self, action):
        self._emit("action", action)

    def open_pop_up(self):
        self._dialog._w.base_widget.focus_position = 0
        self._emit("open")
        super().open_pop_up()

    def close_pop_up(self):
        self._emit("close")
        super().close_pop_up()

    def create_pop_up(self):
        return self._dialog

    def get_pop_up_parameters(self):
        width = self._dialog.width + 7
        return {
            'left': 1,
            'top': -1,
            'overlay_width': width,
            'overlay_height': len(self._options) + 3,
            }
