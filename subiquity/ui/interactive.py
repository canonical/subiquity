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

from urwid import (Edit, IntEdit, RadioButton, WidgetWrap)
import logging

log = logging.getLogger("subiquity.ui.input")


class StringEditor(WidgetWrap):
    """ Edit input class

    Initializes and Edit object and attachs its result
    to the `value` accessor.
    """
    def __init__(self, caption, **kwargs):
        self._edit = Edit(caption=caption, **kwargs)
        super().__init__(self._edit)

    @property
    def value(self):
        return self._edit.get_edit_text()


class PasswordEditor(StringEditor):
    """ Password input prompt with masking
    """
    def __init__(self, caption, mask="*"):
        super().__init__(caption, mask=mask)


class IntegerEditor(WidgetWrap):
    """ IntEdit input class
    """
    def __init__(self, caption, default=0):
        self._edit = IntEdit(caption=caption, default=default)
        super().__init__(self._edit)

    @property
    def value(self):
        return self._edit.get_edit_text()


class Selector(WidgetWrap):
    """ Radio selection list of options
    """
    def __init__(self, opts):
        """
        :param list opts: list of options to display
        """
        self.opts = opts
        self.group = []
        self._add_options()

    def _add_options(self):
        for item in self.opts:
            RadioButton(self.group, item)

    @property
    def value(self):
        for item in self.group:
            log.debug(item)
            if item.get_state():
                return item.label
        return "Unknown option"
