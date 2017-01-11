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

from urwid import (
    ACTIVATE,
    AttrWrap,
    connect_signal,
    Edit,
    Filler,
    IntEdit,
    LineBox,
    Pile,
    PopUpLauncher,
    SelectableIcon,
    TOP,
    WidgetWrap,
    )
import logging
import re

log = logging.getLogger("subiquitycore.ui.input")


class StringEditor(WidgetWrap):
    """ Edit input class

    Initializes and Edit object and attachs its result
    to the `value` accessor.
    """
    def __init__(self, caption, **kwargs):
        self._edit = Edit(caption=caption, **kwargs)
        self.error = None
        super().__init__(self._edit)

    def keypress(self, size, key):
        if self.error:
            self._edit.set_edit_text("")
            self.error = None
        return super().keypress(size, key)

    def set_error(self, msg):
        self.error = msg
        return self._edit.set_edit_text(msg)

    @property
    def value(self):
        return self._edit.get_edit_text()

    @value.setter  # NOQA
    def value(self, value):
        self._edit.set_edit_text(value)


class PasswordEditor(StringEditor):
    """ Password input prompt with masking
    """
    def __init__(self, caption, mask="*"):
        super().__init__(caption, mask=mask)


class RealnameEditor(StringEditor):
    """ Username input prompt with input rules
    """

    def keypress(self, size, key):
        ''' restrict what chars we allow for username '''

        realname = r'[a-zA-Z0-9_\- ]'
        if re.match(realname, key) is None:
            return False

        return super().keypress(size, key)


class EmailEditor(StringEditor):
    """ Email input prompt with input rules
    """

    def keypress(self, size, key):
        ''' restrict what chars we allow for username '''

        realname = r'[-a-zA-Z0-9_.@+=]'
        if re.match(realname, key) is None:
            return False

        return super().keypress(size, key)


class UsernameEditor(StringEditor):
    """ Username input prompt with input rules
    """

    def keypress(self, size, key):
        ''' restrict what chars we allow for username '''

        userlen = len(self.value)
        if userlen == 0:
            username = r'[a-z_]'
        else:
            username = r'[a-z0-9_-]'

        # don't allow non username chars
        if re.match(username, key) is None:
            return False

        return super().keypress(size, key)


class MountEditor(StringEditor):
    """ Mountpoint input prompt with input rules
    """

    def keypress(self, size, key):
        ''' restrict what chars we allow for mountpoints '''

        mountpoint = r'[a-zA-Z0-9_/\.\-]'
        if re.match(mountpoint, key) is None:
            return False

        return super().keypress(size, key)


class IntegerEditor(WidgetWrap):
    """ IntEdit input class
    """
    def __init__(self, caption, default=0):
        self._edit = IntEdit(caption=caption, default=default)
        super().__init__(self._edit)

    @property
    def value(self):
        return self._edit.get_edit_text()


class _PopUpButton(SelectableIcon):
    """It looks like a radio button, but it just emits 'click' on activation."""

    signals = ['click']

    states = {
        True: "(X) ",
        False: "( ) ",
        }

    def __init__(self, option, state):
        super().__init__(self.states[state] + option, 4)

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
            btn = _PopUpButton(option, state=i==cur_index)
            connect_signal(btn, 'click', self.click, i)
            group.append(btn)
        pile = Pile(group)
        pile.set_focus(group[cur_index])
        fill = Filler(pile, valign=TOP)
        super().__init__(LineBox(AttrWrap(fill, 'menu_button')))

    def click(self, btn, index):
        self.parent.index = index
        self.parent.close_pop_up()


class Selector(PopUpLauncher):
    """A widget that allows the user to chose between options by popping up this list of options.

    (A bit like <select> in an HTML form).
    """

    def __init__(self, opts, index=0):
        self._options = opts
        self._button = SelectableIcon("", 0)
        self.index = index
        super().__init__(self._button)

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        self.open_pop_up()

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, val):
        self._button.set_text(self._options[val])
        self._index = val

    @property
    def value(self):
        return self._options[self._index]

    def create_pop_up(self):
        return _PopUpSelectDialog(self, self.index)

    def get_pop_up_parameters(self):
        width = max(map(len, self._options)) + 7 # longest option + line on left, "(?) ", space, line on right
        return {'left':-5, 'top':-self.index-1, 'overlay_width':width, 'overlay_height':len(self._options) + 2}


class YesNo(Selector):
    """ Yes/No selector
    """
    def __init__(self):
        opts = ['Yes', 'No']
        super().__init__(opts)
