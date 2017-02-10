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

from urwid import AttrMap, Text, WidgetDisable, WidgetWrap

from subiquitycore.ui.container import Pile
from subiquitycore.ui.utils import Color


class Toggleable(WidgetWrap):

    def __init__(self, original, active_color):
        self.original = original
        self.active_color = active_color
        self.enabled = False
        self.enable()

    def enable(self):
        if not self.enabled:
            self._w = AttrMap(self.original, self.active_color, self.active_color + ' focus')
            self.enabled = True

    def disable(self):
        if self.enabled:
            self._w = WidgetDisable(Color.info_minor(self.original))
            self.enabled = False


class ValidatingWidgetSet(WidgetWrap):

    signals = ['validated']

    def __init__(self, captioned, decorated, input, validator):
        self.captioned = captioned
        self.decorated = decorated
        self.input = input
        self.validator = validator
        self.in_error = False
        super().__init__(Pile([captioned]))

    def disable(self):
        self.decorated.disable()
        self.hide_error()

    def enable(self):
        self.decorated.enable()
        self.validate()

    def set_error(self, err_msg):
        in_error = True
        if isinstance(err_msg, tuple):
            if len(err_msg) == 3:
                color, err_msg, in_error = err_msg
            else:
                color, err_msg = err_msg
        else:
            color = 'info_error'
        e = AttrMap(Text(err_msg, align="center"), color)
        t = (e, self._w.options('pack'))
        if len(self._w.contents) > 1:
            self._w.contents[1] = t
        else:
            self._w.contents.append(t)
        self.in_error = in_error

    def hide_error(self):
        if len(self._w.contents) > 1:
            self._w.contents = self._w.contents[:1]
        self.in_error = False

    def has_error(self):
        return self.in_error

    def validate(self):
        if self.validator is not None:
            err = self.validator()
            if err is None:
                self.hide_error()
            else:
                self.set_error(err)
            self._emit('validated')

    def lost_focus(self):
        self.validate()

