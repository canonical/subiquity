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
        self.ipv4_info = Pile(self._build_gateway_ipv4_info())
        self.ipv4_method = Pile(self._build_ipv4_method_buttons())
        self.ipv6_info = Pile(self._build_gateway_ipv6_info())
        self.ipv6_method = Pile(self._build_ipv6_method_buttons())
        body = [
            Padding.center_79(self.ipv4_info),
            Padding.center_79(self.ipv4_method),
            Padding.line_break(""),
            Padding.line_break(""),
            Padding.center_79(self.ipv6_info),
            Padding.center_79(self.ipv6_method),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        super().__init__(ListBox(body))

    def _build_gateway_ipv4_info(self):
        addresses = self.iface_obj.ipv4_addresses
        ips = self.iface_obj.ip4
        methods = self.iface_obj.ip4_methods
        providers = self.iface_obj.ip4_providers
        dhcp4 = self.iface_obj.dhcp4

        if dhcp4:
            punct = ":" if len(ips) else "."
            p = [Text("Will use DHCP for IPv4" + punct)]

            for idx in range(len(ips)):
                if methods[idx] == "manual":
                    gw_info = (str(ips[idx]) + (" provided by ") + methods[idx])
                else:
                    gw_info = (str(ips[idx]) + (" provided by ") + methods[idx] +
                                (" from ") + providers[idx])
                p.append(Color.info_minor(Text(gw_info)))
        elif not dhcp4 and len(addresses) > 0:
            p = [Text("Will use static addresses for IPv4:")]
            for idx in range(len(addresses)):
                p.append(Color.info_minor(Text(addresses[idx])))
        else:
            p = [Text("IPv4 is not configured.")]

        return p

    def _build_gateway_ipv6_info(self):
        addresses = self.iface_obj.ipv6_addresses
        ips = self.iface_obj.ip6
        methods = self.iface_obj.ip6_methods
        providers = self.iface_obj.ip6_providers
        dhcp6 = self.iface_obj.dhcp6

        if dhcp6:
            punct = ":" if len(ips) else "."
            p = [Text("Will use DHCP for IPv6" + punct)]

            for idx in range(len(ips)):
                if methods[idx] == "manual":
                    gw_info = (str(ips[idx]) + (" provided by ") + methods[idx])
                else:
                    gw_info = (str(ips[idx]) + (" provided by ") + methods[idx] +
                                (" from ") + providers[idx])
                p.append(Color.info_minor(Text(gw_info)))
        elif not dhcp6 and len(addresses) > 0:
            p = [Text("Will use static addresses for IPv6:")]
            for idx in range(len(addresses)):
                p.append(Color.info_minor(Text(addresses[idx])))
        else:
            p = [Text("IPv6 is not configured.")]

        return p

    def _build_ipv4_method_buttons(self):
        dhcp4 = self.iface_obj.dhcp6

        button_padding = 40

        buttons = []
        btn = menu_btn(label="Use a static IPv4 configuration",
                       on_press=self.show_ipv4_configuration)
        buttons.append(Color.menu_button(btn, focus_map="menu_button focus"))
        btn = menu_btn(label="Use DHCPv4 on this interface",
                       on_press=self.enable_dhcp4)
        buttons.append(Color.menu_button(btn, focus_map="menu_button focus"))
        btn = menu_btn(label="Do not use",
                       on_press=self.clear_ipv4)
        buttons.append(Color.menu_button(btn, focus_map="menu_button focus"))

        padding = getattr(Padding, 'left_{}'.format(button_padding))
        buttons = [ padding(button) for button in buttons ]

        return buttons

    def _build_ipv6_method_buttons(self):
        dhcp6 = self.iface_obj.dhcp6

        button_padding = 40

        buttons = []
        btn = menu_btn(label="Use a static IPv6 configuration",
                       on_press=self.show_ipv6_configuration)
        buttons.append(Color.menu_button(btn, focus_map="menu_button focus"))
        btn = menu_btn(label="Use DHCPv6 on this interface",
                       on_press=self.enable_dhcp6)
        buttons.append(Color.menu_button(btn, focus_map="menu_button focus"))
        btn = menu_btn(label="Do not use",
                       on_press=self.clear_ipv6)
        buttons.append(Color.menu_button(btn, focus_map="menu_button focus"))

        padding = getattr(Padding, 'left_{}'.format(button_padding))
        buttons = [ padding(button) for button in buttons ]

        return buttons

    def _build_buttons(self):
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
        ]
        return Pile(buttons)

    def update_interface(self):
        self.ipv4_info.contents = [ (obj, ('pack', None)) for obj in self._build_gateway_ipv4_info() ]
        self.ipv6_info.contents = [ (obj, ('pack', None)) for obj in self._build_gateway_ipv6_info() ]

    def clear_ipv4(self, btn):
        self.iface_obj.remove_ipv4_networks()
        self.model.set_default_v4_gateway(None, None)
        self.update_interface()

    def clear_ipv6(self, btn):
        self.iface_obj.remove_ipv6_networks()
        self.model.set_default_v6_gateway(None, None)
        self.update_interface()

    def enable_dhcp4(self, btn):
        self.clear_ipv4(btn)
        self.iface_obj.dhcp4 = True
        self.update_interface()

    def enable_dhcp6(self, btn):
        self.clear_ipv6(btn)
        self.iface_obj.dhcp6 = True
        self.update_interface()

    def show_ipv4_configuration(self, btn):
        self.signal.emit_signal(
            'menu:network:main:configure-ipv4-interface', self.iface)

    def show_ipv6_configuration(self, btn):
        log.debug("calling menu:network:main:configure-ipv6-interface")
        # TODO: implement UI for configuring static IPv6.
        # self.signal.emit_signal(
        #     'menu:network:main:configure-ipv6-interface', self.iface)

    def done(self, result):
        self.signal.prev_signal()
