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

import logging
from urwid import Text

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import cancel_btn, done_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.utils import Color, Padding

log = logging.getLogger('subiquity.ceph')


class CephDiskView(BaseView):
    def __init__(self, model, signal):
        self.model = model
        self.signal = signal
        self.ceph_mon = StringEditor()
        self.username = StringEditor()
        self.ceph_key = StringEditor()
        self.pool = []
        body = [
            Padding.center_50(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        super().__init__(ListBox(body))

    def _build_model_inputs(self):
        items = [
            Columns(
                [
                    ("weight", 0.2, Text("Ceph MON", align="right")),
                    ("weight", 0.3, Color.string_input(self.ceph_mon))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Username",
                                         align="right")),
                    ("weight", 0.3, Color.string_input(self.username))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Key", align="right")),
                    ("weight", 0.3, Color.string_input(self.ceph_key))
                ],
                dividechars=4
            )
        ]
        return Pile(items)

    def _build_buttons(self):
        buttons = [
            done_btn(on_press=self.done),
            cancel_btn(on_press=self.cancel),
        ]
        return Pile(buttons)

    def done(self, result):
        self.signal.emit_signal('ceph:finish')

    def cancel(self, button):
        self.signal.emit_signal(self.model.get_previous_signal)
