# Copyright 2016 Canonical, Ltd.
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

import logging
import socket

from urwid import (Pile, Columns, Text, ListBox)
from subiquitycore.ui.buttons import done_btn, cancel_btn
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.view import BaseView

log = logging.getLogger("subiquitycore.views.hostname")


'''
+----------------------------------------------+
|                                              |
| Enter the hostname to use for the device     |
|                                              |
|              +-------------------------+     |
|    Hostname: | localhost               |     |
|              +-------------------------+     |
|                                              |
|                                              |
|                         +--------+           |
|                         | Done   |           |
|                         +--------+           |
|                         | Cancel |           |
|                         +--------+           |
|                                              |
+----------------------------------------------+
'''

class SubmittingHostnameEditor(StringEditor):

    def __init__(self, mainview):
        self.mainview = mainview
        super().__init__(caption="")

    def keypress(self, size, key):
        if key == 'enter':
            self.mainview.done(None)
            return None
        else:
            return super().keypress(size, key)


class HostnameView(BaseView):

    def __init__(self, controller):
        self.controller = controller
        self.hostname = SubmittingHostnameEditor(self)
        self.hostname.value = socket.gethostname()
        self.error = Text("", align="center")

        body = [
            Padding.center_90(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_90(Color.info_error(self.error)),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons()),
        ]
        super().__init__(ListBox(body))

    def _build_model_inputs(self):
        sl = [
            Columns(
                [
                    ("weight", 0.2, Text("Hostname:", align="right")),
                    ("weight", 0.3,
                     Color.string_input(self.hostname,
                                        focus_map="string_input focus"))
                ],
                dividechars=4
            ),
        ]
        return Pile(sl)

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def cancel(self, button):
        self.controller.cancel()

    def done(self, button):
        if len(self.hostname.value) < 1:
            self.error.set_text("Please enter a non-empty name.")
            return
        self.controller.done(self.hostname.value)
