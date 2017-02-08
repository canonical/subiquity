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

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import done_btn, menu_btn
from subiquitycore.ui.container import ListBox, Pile
from subiquitycore.ui.utils import Color, Padding
from subiquitycore.ui.views.network import _build_gateway_ip_info_for_version, _build_wifi_info
import logging

log = logging.getLogger('subiquitycore.network.network_configure_interface')


class NetworkConfigureInterfaceView(BaseView):
    def __init__(self, model, controller, name):
        self.model = model
        self.controller = controller
        self.dev = self.model.get_netdev_by_name(name)
        self._build_widgets()
        super().__init__(ListBox(self._build_body()))

    def _build_widgets(self):
        self.ipv4_info = Pile(_build_gateway_ip_info_for_version(self.dev, 4))
        self.ipv4_method = Pile(self._build_ipv4_method_buttons())
        self.ipv6_info = Pile(_build_gateway_ip_info_for_version(self.dev, 6))
        self.ipv6_method = Pile(self._build_ipv6_method_buttons())
        if self.dev.type == 'wlan':
            self.wifi_info = Pile(_build_wifi_info(self.dev))
            self.wifi_method = Pile(self._build_wifi_config())

    def _build_body(self):
        body = []
        if self.dev.type == 'wlan':
            body.extend([
                Padding.center_79(self.wifi_info),
                Padding.center_79(self.wifi_method),
                Padding.line_break(""),
                ])
        body.extend([
            Padding.center_79(self.ipv4_info),
            Padding.center_79(self.ipv4_method),
            Padding.line_break(""),
            Padding.center_79(self.ipv6_info),
            Padding.center_79(self.ipv6_method),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ])
        return body

    def _build_ipv4_method_buttons(self):
        button_padding = 70

        buttons = []
        btn = menu_btn(label="Use a static IPv4 configuration",
                       on_press=self.show_ipv4_configuration)
        buttons.append(Color.menu_button(btn))
        btn = menu_btn(label="Use DHCPv4 on this interface",
                       on_press=self.enable_dhcp4)
        buttons.append(Color.menu_button(btn))
        btn = menu_btn(label="Do not use",
                       on_press=self.clear_ipv4)
        buttons.append(Color.menu_button(btn))

        padding = getattr(Padding, 'left_{}'.format(button_padding))
        buttons = [ padding(button) for button in buttons ]

        return buttons

    def _build_ipv6_method_buttons(self):
        button_padding = 70

        buttons = []
        btn = menu_btn(label="Use a static IPv6 configuration",
                       on_press=self.show_ipv6_configuration)
        buttons.append(Color.menu_button(btn))
        btn = menu_btn(label="Use DHCPv6 on this interface",
                       on_press=self.enable_dhcp6)
        buttons.append(Color.menu_button(btn))
        btn = menu_btn(label="Do not use",
                       on_press=self.clear_ipv6)
        buttons.append(Color.menu_button(btn))

        padding = getattr(Padding, 'left_{}'.format(button_padding))
        buttons = [ padding(button) for button in buttons ]

        return buttons


    def _build_wifi_config(self):
        btn = menu_btn(label="Configure WIFI settings", on_press=self.show_wlan_configuration)
        return [Padding.left_70(Color.menu_button(btn))]

    def _build_buttons(self):
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done),
        ]
        return Pile(buttons)

    def refresh_model_inputs(self):
        try:
            self.dev = self.model.get_netdev_by_name(self.dev.name)
        except KeyError:
            # The interface is gone
            self.controller.prev_view()
            return
        if self.dev.type == 'wlan':
            self.wifi_info.contents = [ (obj, ('pack', None)) for obj in _build_wifi_info(self.dev) ]
        self.ipv4_info.contents = [ (obj, ('pack', None)) for obj in _build_gateway_ip_info_for_version(self.dev, 4) ]
        self.ipv6_info.contents = [ (obj, ('pack', None)) for obj in _build_gateway_ip_info_for_version(self.dev, 6) ]

    def clear_ipv4(self, btn):
        self.dev.remove_ip_networks_for_version(4)
        self.dev.remove_nameservers()
        self.model.set_default_v4_gateway(None, None)
        self.refresh_model_inputs()

    def clear_ipv6(self, btn):
        self.dev.remove_ip_networks_for_version(6)
        self.dev.remove_nameservers()
        self.model.set_default_v6_gateway(None, None)
        self.refresh_model_inputs()

    def enable_dhcp4(self, btn):
        self.clear_ipv4(btn)
        self.dev.remove_nameservers()
        self.dev.dhcp4 = True
        self.refresh_model_inputs()

    def enable_dhcp6(self, btn):
        self.clear_ipv6(btn)
        self.dev.remove_nameservers()
        self.dev.dhcp6 = True
        self.refresh_model_inputs()

    def show_wlan_configuration(self, btn):
        self.controller.network_configure_wlan_interface(self.dev.name)

    def show_ipv4_configuration(self, btn):
        self.controller.network_configure_ipv4_interface(self.dev.name)

    def show_ipv6_configuration(self, btn):
        self.controller.network_configure_ipv6_interface(self.dev.name)

    def done(self, result):
        self.controller.prev_view()
