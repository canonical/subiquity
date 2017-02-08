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

""" Dummy placeholder widget
"""

from urwid import (WidgetWrap, Text, Pile, ListBox)
from subiquitycore.ui.buttons import cancel_btn
from subiquitycore.ui.utils import Padding, Color


class DummyView(WidgetWrap):
    def __init__(self, signal):
        self.signal = signal
        self.body = [
            Padding.center_79(Text("This view is not yet implemented.")),
            Padding.line_break(""),
            Padding.center_79(Color.info_minor(Text("A place holder widget"))),
            Padding.line_break(""),
            Padding.center_79(self._build_buttons())
        ]
        super().__init__(ListBox(self.body))

    def _build_buttons(self):
        buttons = [
            Color.button(cancel_btn(label="Back to Start",
                                    on_press=self.cancel)),
        ]
        return Pile(buttons)

    def cancel(self, result):
        self.signal.emit_signal('menu:welcome:main')
