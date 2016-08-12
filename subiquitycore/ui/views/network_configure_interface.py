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
from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import done_btn, menu_btn
from subiquitycore.ui.utils import Color, Padding
import logging

log = logging.getLogger('subiquitycore.network.network_configure_interface')


class NetworkConfigureInterfaceView(BaseView):
    def __init__(self, model, signal, iface):
        self.model = model
        self.signal = signal
        self.iface = iface
        self.iface_obj = self.model.get_interface(iface)
        body = [
            Padding.center_79(self._build_gateway_ipv4_info()),
            Padding.center_79(self._build_manual_ipv4_button()),
            Padding.line_break(""),
            Padding.line_break(""),
            Padding.center_79(self._build_gateway_ipv6_info()),
            Padding.center_79(self._build_manual_ipv6_button()),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        super().__init__(ListBox(body))

    def _build_gateway_ipv4_info(self):
        header = ("IPv4 not configured")
        gw_info = None
        ips = self.iface_obj.ip4
        methods = self.iface_obj.ip4_methods
        providers = self.iface_obj.ip4_providers

        for idx in range(len(ips)):
            if not (None in [ips[idx], providers[idx], methods[idx]]):
                if methods[idx] in ['dhcp']:
                    header = ("Will use DHCP for IPv4:")
                else:
                    header = ("Will use static for IPv4:")
                gw_info = (str(ips[idx]) + (" provided by ") + methods[idx] +
                           (" from ") + providers[idx])

            p = [Text(header)]
            if gw_info:
                p.append(Text(gw_info))

        return Pile(p)

    def _build_gateway_ipv6_info(self):
        header = ("IPv6 not configured")
        gw_info = None

        p = [Text(header)]
        if gw_info:
            p.append(Text(gw_info))

        return Pile(p)

    def _build_manual_ipv4_button(self):
        btn = menu_btn(label="Switch to manual IPv4 configuration",
                       on_press=self.show_ipv4_configuration)
        return Pile([Color.menu_button(btn, focus_map="menu_button focus")])

    def _build_manual_ipv6_button(self):
        text = ("Switch to manual IPv6 configuration")
        # FIXME: ipv6 testing
        # btn = menu_btn(label=text,
        #                  on_press=self.show_ipv6_configuration)
        # mb = Color.menu_button(btn, focus_map="menu_button focus")
        mb = Color.info_minor(Text("  " + text))
        return Pile([mb])

    def _build_buttons(self):
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
        ]
        return Pile(buttons)

    def show_ipv4_configuration(self, btn):
        self.signal.emit_signal(
            'menu:network:main:configure-ipv4-interface', self.iface)

    def show_ipv6_configuration(self, btn):
        self.signal.emit_signal(
            'menu:network:main:configure-ipv6-interface', self.iface)

    def done(self, result):
        self.signal.prev_signal()
