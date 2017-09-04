# Copyright 2017 Canonical, Ltd.
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
    connect_signal,
    Filler,
    LineBox,
    PopUpLauncher,
    SelectableIcon,
    Text,
    TOP,
    WidgetWrap,
    )

from subiquitycore.ui.container import Pile


class _PopUpButton(SelectableIcon):
    """It looks a bit like a radio button, but it just emits 'click' on activation."""

    signals = ['click']

    states = {
        True: "(+) ",
        False: "( ) ",
        }

    def __init__(self, option, state):
        p = self.states[state]
        super().__init__(p + option, len(p))

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        self._emit('click')


class _PopUpSelectDialog(WidgetWrap):
    """A list of PopUpButtons with a box around them."""

    def __init__(self, parent, cur_index):
        self.parent = parent
        group = []
        for i, option in enumerate(self.parent._options):
            if option.enabled:
                btn = _PopUpButton(option.label, state=i==cur_index)
                connect_signal(btn, 'click', self.click, i)
                group.append(AttrWrap(btn, 'menu_button', 'menu_button focus'))
            else:
                btn = Text("    " + option.label)
                group.append(AttrWrap(btn, 'info_minor'))
        pile = Pile(group)
        pile.set_focus(group[cur_index])
        fill = Filler(pile, valign=TOP)
        super().__init__(LineBox(fill))

    def click(self, btn, index):
        self.parent.index = index
        self.parent.close_pop_up()

    def keypress(self, size, key):
        if key == 'esc':
            self.parent.close_pop_up()
        else:
            return super().keypress(size, key)


class SelectorError(Exception):
    pass


class Option:

    def __init__(self, val):
        if not isinstance(val, tuple):
            if not isinstance(val, str):
                raise SelectorError("invalid option %r", val)
            self.label = val
            self.enabled = True
            self.value = val
        elif len(val) == 1:
            self.label = val[0]
            self.enabled = True
            self.value = val[0]
        elif len(val) == 2:
            self.label = val[0]
            self.enabled = val[1]
            self.value = val[0]
        elif len(val) == 3:
            self.label = val[0]
            self.enabled = val[1]
            self.value = val[2]
        else:
            raise SelectorError("invalid option %r", val)


class Selector(PopUpLauncher):
    """A widget that allows the user to chose between options by popping up a list of options.

    (A bit like <select> in an HTML form).
    """

    _prefix = "(+) "

    signals = ['select']

    def __init__(self, opts, index=0):
        self._options = []
        for opt in opts:
            if not isinstance(opt, Option):
                opt = Option(opt)
            self._options.append(opt)
        self._button = SelectableIcon(self._prefix, len(self._prefix))
        self._set_index(index)
        super().__init__(self._button)

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        self.open_pop_up()

    def _set_index(self, val):
        self._button.set_text(self._prefix + self._options[val].label)
        self._index = val

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, val):
        self._emit('select', self._options[val].value)
        self._set_index(val)

    def option_by_label(self, label):
        for opt in self._options:
            if opt.label == label:
                return opt

    def option_by_value(self, value):
        for opt in self._options:
            if opt.value == value:
                return opt

    def option_by_index(self, index):
        return self._options[index]

    @property
    def value(self):
        return self._options[self._index].value

    @value.setter
    def value(self, val):
        for i, opt in enumerate(self._options):
            if opt.value == val:
                self.index = i
                return
        raise AttributeError("cannot set value to %r", val)

    def create_pop_up(self):
        return _PopUpSelectDialog(self, self.index)

    def get_pop_up_parameters(self):
        width = max([len(o.label) for o in self._options]) \
          + len(self._prefix) +  3 # line on left, space, line on right
        return {'left':-1, 'top':-self.index-1, 'overlay_width':width, 'overlay_height':len(self._options) + 2}
