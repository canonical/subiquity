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

""" Re-usable input widgets
"""

from functools import partial
import logging
import re

from urwid import (
    ACTIVATE,
    AttrWrap,
    connect_signal,
    Edit,
    Filler,
    IntEdit,
    LineBox,
    PopUpLauncher,
    SelectableIcon,
    Text,
    TOP,
    WidgetWrap,
    )

from subiquitycore.ui.buttons import PlainButton
from subiquitycore.ui.container import Pile
from subiquitycore.ui.utils import Color, Padding

log = logging.getLogger("subiquitycore.ui.input")


class StringEditor(Edit):
    """ Edit input class

    Attaches its result to the `value` accessor.
    """

    @property
    def value(self):
        return self.get_edit_text()

    @value.setter  # NOQA
    def value(self, value):
        self.set_edit_text(value)


class PasswordEditor(StringEditor):
    """ Password input prompt with masking
    """
    def __init__(self, mask="*"):
        super().__init__(mask=mask)


class RestrictedEditor(StringEditor):
    """Editor that only allows certain characters."""

    def __init__(self, allowed=None):
        super().__init__()
        self.matcher = re.compile(allowed)

    def valid_char(self, ch):
        return len(ch) == 1 and self.matcher.match(ch) is not None


RealnameEditor = partial(RestrictedEditor, r'[a-zA-Z0-9_\- ]')
EmailEditor = partial(RestrictedEditor, r'[-a-zA-Z0-9_.@+=]')


class UsernameEditor(StringEditor):
    """ Username input prompt with input rules
    """

    def keypress(self, size, key):
        ''' restrict what chars we allow for username '''
        if self._command_map[key] is not None:
            return super().keypress(size, key)
        new_text = self.insert_text_result(key)[0]
        username = r'[a-z_][a-z0-9_-]*'
        # don't allow non username chars
        if new_text != "" and re.match(username, new_text) is None:
            return False
        return super().keypress(size, key)


class IntegerEditor(WidgetWrap):
    """ IntEdit input class
    """
    def __init__(self, default=0):
        self._edit = IntEdit(default=default)
        super().__init__(self._edit)

    @property
    def value(self):
        return self._edit.value()

    @value.setter
    def value(self, val):
        return self._edit.set_edit_text(str(val))


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
            if option[1]:
                btn = _PopUpButton(option[0], state=i==cur_index)
                connect_signal(btn, 'click', self.click, i)
                group.append(AttrWrap(btn, 'menu_button', 'menu_button focus'))
            else:
                btn = Text("    " + option[0])
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

class Selector(PopUpLauncher):
    """A widget that allows the user to chose between options by popping up this list of options.

    (A bit like <select> in an HTML form).
    """

    _prefix = "(+) "

    signals = ['select']

    def __init__(self, opts, index=0):
        self._options = []
        for opt in opts:
            if not isinstance(opt, tuple):
                if not isinstance(opt, str):
                    raise SelectorError("invalid option %r", opt)
                opt = (opt, True, opt)
            elif len(opt) == 1:
                opt = (opt[0], True, opt[0])
            elif len(opt) == 2:
                opt = (opt[0], opt[1], opt[0])
            elif len(opt) != 3:
                raise SelectorError("invalid option %r", opt)
            self._options.append(opt)
        self._button = SelectableIcon(self._prefix, len(self._prefix))
        self._set_index(index)
        super().__init__(self._button)

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        self.open_pop_up()

    def _set_index(self, val):
        self._button.set_text(self._prefix + self._options[val][0])
        self._index = val

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, val):
        self._emit('select', self._options[val][2])
        self._set_index(val)

    @property
    def value(self):
        return self._options[self._index][2]

    @value.setter
    def value(self, val):
        for i, (label, enabled, value) in enumerate(self._options):
            if value == val:
                self.index = i
                return
        raise AttributeError("cannot set value to %r", val)

    def create_pop_up(self):
        return _PopUpSelectDialog(self, self.index)

    def get_pop_up_parameters(self):
        width = max([len(o[0]) for o in self._options]) \
          + len(self._prefix) +  3 # line on left, space, line on right
        return {'left':-1, 'top':-self.index-1, 'overlay_width':width, 'overlay_height':len(self._options) + 2}


class YesNo(Selector):
    """ Yes/No selector
    """
    def __init__(self):
        opts = ['Yes', 'No']
        super().__init__(opts)


class _HelpDisplay(WidgetWrap):
    def __init__(self, closer, help_text):
        self._closer = closer
        button = Color.button(PlainButton(label="Close", on_press=lambda btn:self._closer()))
        super().__init__(LineBox(Pile([Text(help_text), Padding.fixed_10(button)]), title="Help"))
    def keypress(self, size, key):
        if key == 'esc':
            self._closer()
        else:
            return super().keypress(size, key)


class Help(WidgetWrap):

    def __init__(self, view, help_text):
        self._view = view
        self._help_text = help_text
        self._button = Padding.fixed_3(Color.button(SelectableIcon("[?]", 1)))
        super().__init__(self._button)

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        self._view.show_overlay(_HelpDisplay(self._view.remove_overlay, self._help_text))
