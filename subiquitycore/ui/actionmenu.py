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
    )

from subiquitycore.ui.buttons import delete_btn, menu_btn
from subiquitycore.ui.container import Columns, ListBox
from subiquitycore.ui.selector import Option


def demarkup(s):
    if isinstance(s, str):
        return s
    if isinstance(s, tuple):
        return demarkup(s[1])
    if isinstance(s, list):
        return [demarkup(x) for x in s]

def markup_length(s):
    s = demarkup(s)
    if isinstance(s, str):
        return len(s)
    if isinstance(s, list):
        return sum(markup_length(x) for x in s)

class _ActionMenuDialog(WidgetWrap):
    """A list of menu_btns with a box around them."""

    def __init__(self, parent):
        self.parent = parent
        close = Button("(close)")
        connect_signal(close, "click", self.close)
        del close.base_widget._w.contents[2] # something of a hack...
        group = [close]
        #group = []
        for i, option in enumerate(self.parent._options):
            if option.enabled:
                if option.value == 'delete':
                    btn = delete_btn(option.label, on_press=self.click, user_arg=option.value)
                    del btn.base_widget._w.contents[0] # something of a hack...
                    btn.base_widget._w.contents[1] = (Text(">"), btn.base_widget._w.options('given', 1))
                else:
                    btn = menu_btn(option.label, on_press=self.click, user_arg=option.value)
                    del btn.base_widget._w.contents[0] # something of a hack...
                group.append(btn)
            else:
                btn = Columns((Text(demarkup(option.label)), ('fixed', 1, Text(">"))))
                group.append(AttrWrap(btn, 'info_minor'))
        list_box = ListBox(group)
        super().__init__(LineBox(list_box))

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


class SelectorError(Exception):
    pass


class ActionMenu(PopUpLauncher):

    icon = "[\N{GREEK CAPITAL LETTER XI}]"

    signals = ['action']

    def __init__(self, opts):
        self._options = []
        for opt in opts:
            if not isinstance(opt, Option):
                opt = Option(opt)
            self._options.append(opt)
        self._button = SelectableIcon(self.icon, 1)
        super().__init__(self._button)

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        self.open_pop_up()

    def _set_index(self, val):
        self._button.set_text(self._prefix + self._options[val].label)
        self._index = val

    def _action(self, action):
        self._emit("action", action)

    def create_pop_up(self):
        return _ActionMenuDialog(self)

    def get_pop_up_parameters(self):
        width = max([markup_length(o.label) for o in self._options]) + 5
        return {'left':0, 'top':1, 'overlay_width':width, 'overlay_height':len(self._options) + 3}
