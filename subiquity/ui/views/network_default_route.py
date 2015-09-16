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

from urwid import Text, Pile, ListBox
from subiquity.view import ViewPolicy
from subiquity.ui.buttons import cancel_btn, done_btn
from subiquity.ui.utils import Color, Padding
import logging

log = logging.getLogger('subiquity.network.set_default_route')


class NetworkSetDefaultRouteView(ViewPolicy):
    def __init__(self, model, signal):
        self.model = model
        self.signal = signal
        self.is_manual = False
        body = [
            Padding.center_50(self._build_disk_selection()),
            Padding.line_break(""),
            Padding.center_50(self._build_raid_configuration()),
            Padding.line_break(""),
            Padding.center_20(self._build_buttons())
        ]
        super().__init__(ListBox(body))

    def _build_default_routes(self):
        items = [
            Text("Please set the default gateway:"),
            Color.menu_button(done_btn(label="192.168.9.1 (em1, em2)",
                                       on_press=self.done),
                              focus_map="menu_button focus"),
            Color.menu_button(
                done_btn(label="Specify the default route manually",
                         on_press=self.set_manually),
                focus_map="menu_button focus")
        ]
        return Pile(items)

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def set_manually(self, result):
        self.is_manual = True
        self.signal.emit_signal('refresh')

    def done(self, result):
        self.signal.emit_signal('network:show')

    def cancel(self, button):
        self.signal.emit_signal(self.model.get_previous_signal)
