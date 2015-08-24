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

""" Welcome

Welcome provides user with language selection

"""
import logging
from urwid import (Pile, emit_signal)
from subiquity.ui.widgets import Box
from subiquity.ui.buttons import done_btn, cancel_btn
from subiquity.ui.interactive import StringEditor, PasswordEditor
from subiquity.ui.utils import Padding, Color
from subiquity.view import ViewPolicy

log = logging.getLogger("subiquity.views.identity")


class IdentityView(ViewPolicy):
    def __init__(self, model, signal):
        self.model = model
        self.signal = signal
        self.items = []
        self.username = StringEditor(caption="Username: ")
        self.password = PasswordEditor(caption="Password: ")
        self.confirm_password = PasswordEditor(caption="Confirm Password: ")

        body = [
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_20(self._build_buttons()),
        ]
        super().__init__(Box(body))

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button_secondary(cancel, focus_map='button_secondary focus'),
            Color.button_secondary(done, focus_map='button_secondary focus')
        ]
        return Pile(buttons)

    def _build_model_inputs(self):
        sl = [
            self.username,
            self.password,
            self.confirm_password
        ]
        return Pile(sl)

    def done(self, result):
        log.debug("User input: {} {} {}".format(self.username.value,
                                                self.password.value,
                                                self.confirm_password.value))
        result = {
            "username": self.username.value,
            "password": self.password.value,
            "confirm_password": self.confirm_password.value
        }
        log.debug("User input: {}".format(result))
        emit_signal(self.signal, 'installprogress:show')

    def cancel(self, button):
        self.signal.emit_signal("quit")
