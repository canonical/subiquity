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
    Edit,
    IntEdit,
    LineBox,
    SelectableIcon,
    Text,
    WidgetWrap,
    )

from subiquitycore.ui.buttons import close_btn
from subiquitycore.ui.container import Pile
from subiquitycore.ui.selector import Selector
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


class YesNo(Selector):
    """ Yes/No selector
    """
    def __init__(self):
        opts = ['Yes', 'No']
        super().__init__(opts)


class _HelpDisplay(WidgetWrap):
    def __init__(self, closer, help_text):
        self._closer = closer
        button = close_btn(on_press=lambda btn:self._closer())
        super().__init__(LineBox(Pile([Text(help_text), Padding.fixed_10(button)]), title="Help"))


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
