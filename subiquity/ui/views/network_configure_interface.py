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
from subiquity.ui.buttons import done_btn, confirm_btn
from subiquity.ui.utils import Color, Padding
import logging

log = logging.getLogger('subiquity.network.network_configure_interface')


class NetworkConfigureInterfaceView(ViewPolicy):
    def __init__(self, model, signal, iface):
        self.model = model
        self.signal = signal
        self.iface = iface
        body = [
            Padding.center_79(Text("Will use DHCP for IPv4:")),
            Padding.center_79(self._build_gateway_info()),
            Padding.center_79(self._build_manual_ipv4_button()),
            Padding.line_break(""),
            Padding.center_79(Text("Checking IPv6...")),
            Padding.center_79(self._build_manual_ipv6_button()),
            Padding.line_break(""),
            Padding.center_20(self._build_buttons())
        ]
        super().__init__(ListBox(body))

    def _build_gateway_info(self):
        return Pile([Text("<ip> offered by DHCP server <gateway ip>")])

    def _build_manual_ipv4_button(self):
        btn = confirm_btn(label="Switch to manual IPv4 configuration",
                          on_press=self.show_ipv4_configuration)
        return Pile([Color.menu_button(btn, focus_map="menu_button focus")])

    def _build_manual_ipv6_button(self):
        return Pile([Text("Switch to manual IPv6 configuration")])

    def _build_buttons(self):
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
        ]
        return Pile(buttons)

    def show_ipv4_configuration(self, btn):
        self.signal.emit_signal('network:configure-ipv4-interface', self.iface)

    def done(self, result):
        self.signal.emit_signal('network:show')
