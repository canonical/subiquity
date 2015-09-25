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
from urwid import (Text, Filler,
                   Pile)
from subiquity.view import ViewPolicy
from subiquity.ui.buttons import confirm_btn
from subiquity.ui.utils import Padding, Color

log = logging.getLogger("subiquity.ui.views.installprogress")


class ProgressView(ViewPolicy):
    def __init__(self, signal):
        """
        :param output_w: Filler widget to display updated status text
        """
        self.signal = signal
        self.text = Text("Wait for it ...", align="center")
        self.body = [
            Padding.center_79(self.text)
        ]
        self.pile = Pile(self.body)
        super().__init__(Filler(self.pile, valign="middle"))

    def show_finished_button(self):
        w = Padding.center_20(
            Color.button(confirm_btn(label="Reboot now",
                                     on_press=self.reboot),
                         focus_map='button focus'))

        self.pile.contents.append((w, self.pile.options()))
        self.pile.focus_position = 1

    def keypress(self, size, key):
        super().keypress(size, key)
        if key in ['q', 'Q']:
            self.signal.emit_signal('installprogress:curtin-reboot')

    def reboot(self, btn):
        self.signal.emit_signal('installprogress:curtin-reboot')
