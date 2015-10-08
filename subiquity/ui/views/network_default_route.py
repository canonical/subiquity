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
from subiquity.ui.interactive import StringEditor
import logging

log = logging.getLogger('subiquity.network.set_default_route')


class NetworkSetDefaultRouteView(ViewPolicy):
    def __init__(self, model, signal):
        self.model = model
        self.signal = signal
        self.default_gateway_w = None
        body = [
            Padding.center_79(Text("Please set the default gateway:")),
            Padding.line_break(""),
            Padding.center_79(self._build_default_routes()),
            Padding.line_break(""),
            Padding.center_20(self._build_buttons())
        ]
        super().__init__(ListBox(body))

    def _build_default_routes(self):
        ifaces = self.model.get_interfaces()
        items = []
        for iface in ifaces:
            items.append(Padding.center_50(
                Color.menu_button(done_btn(
                    label="{ip} ({iface})".format(
                        ip="FIXME: needs default gateway",
                        iface=iface),
                    on_press=self.done),
                    focus_map="menu_button focus")))
        items.append(Padding.center_50(
            Color.menu_button(
                done_btn(label="Specify the default route manually",
                         on_press=self.show_edit_default_route),
                focus_map="menu_button focus")))
        self.pile = Pile(items)
        return self.pile

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def show_edit_default_route(self, btn):
        log.debug("Re-rendering specify default route")
        self.default_gateway_w = StringEditor(
            caption="Default gateway will be ")
        self.pile.contents[-1] = (Padding.center_50(
            Color.string_input(
                self.default_gateway_w,
                focus_map="string_input focus")), self.pile.options())
        # self.signal.emit_signal('refresh')

    def done(self, result):
        if self.default_gateway_w and self.default_gateway_w.value:
            self.model.default_gateway = self.default_gateway_w.value
        else:
            self.model.default_gateway = result.label
        self.signal.emit_signal('network:show')

    def cancel(self, button):
        self.signal.emit_signal('network:show')
