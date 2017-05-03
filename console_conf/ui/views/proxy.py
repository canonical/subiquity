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

import logging

from urwid import Text
from subiquitycore.ui.buttons import done_btn, cancel_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.view import BaseView

log = logging.getLogger("console_conf.ui.views.proxy")


'''
+---------------------------------------------------+
|                                                   |
| Enter the email address of the account in the     |
| store                                             |
|                                                   |
|                   +-------------------------+     |
|    Email address: |                         |     |
|                   +-------------------------+     |
|                                                   |
|                                                   |
|                         +--------+                |
|                         | Done   |                |
|                         +--------+                |
|                         | Cancel |                |
|                         +--------+                |
|                                                   |
+---------------------------------------------------+
'''


class ProxyView(BaseView):

    def __init__(self, model, controller, opts):
        self.model = model
        self.controller = controller
        self.opts = opts
        self.proxy = StringEditor()
        self.proxy.set_edit_text(model.get_proxy())
        self.error = Text("", align="center")

        body = [
            Padding.center_90(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_90(Color.info_error(self.error)),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons()),
        ]
        super().__init__(ListBox(body))

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key == 'enter':
            self.done(None)
            return None
        else:
            return key

    def _build_model_inputs(self):
        sl = [
            Columns(
                [
                    ("weight", 0.2, Text("Proxy URL:", align="right")),
                    ("weight", 0.3, Color.string_input(self.proxy)),
                ],
                dividechars=4
            ),
        ]
        return Pile(sl)

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done),
            Color.button(cancel),
        ]
        return Pile(buttons)

    def cancel(self, button=None):
        self.controller.cancel()

    def done(self, button):
        self.controller.done(self.proxy.value)
