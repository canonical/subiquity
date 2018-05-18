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
from subiquitycore.ui.buttons import done_btn, menu_btn, _stylized_button
from subiquitycore.ui.container import ListBox, Pile
from subiquitycore.ui.utils import button_pile, Padding
from subiquitycore.ui.views.network import _build_gateway_ip_info_for_version, _build_wifi_info

log = logging.getLogger('subiquitycore.network.network_configure_interface')

choice_btn = _stylized_button("", "", "menu")

class NetworkConfigureInterfaceView(BaseView):

    def __init__(self, model, controller, name):
        self.model = model
        self.controller = controller
        self.dev = self.model.get_netdev_by_name(name)
        self.title = _("Network interface {}").format(name)
        self._build_widgets()
        super().__init__(Pile([
            ('pack', Text("")),
            Padding.center_79(ListBox(self._build_body())),
            ('pack', Text("")),
            ('pack', self._build_buttons()),
            ('pack', Text("")),
            ]))

    def _build_widgets(self):
        self.ipv4_info = Pile(_build_gateway_ip_info_for_version(self.dev, 4))
        self.ipv4_method = Pile(self._build_ipv4_method_buttons())
        self._set_ipv4_prefixes()
        self.ipv6_info = Pile(_build_gateway_ip_info_for_version(self.dev, 6))
        self.ipv6_method = Pile(self._build_ipv6_method_buttons())
        self._set_ipv6_prefixes()
        if self.dev.type == 'wlan':
            self.wifi_info = Pile(_build_wifi_info(self.dev))
            self.wifi_method = Pile(self._build_wifi_config())

    def _build_body(self):
        body = []
        if self.dev.type == 'wlan':
            body.extend([
                self.wifi_info,
                self.wifi_method,
                Padding.line_break(""),
                ])
        body.extend([
            self.ipv4_info,
            self.ipv4_method,
            Padding.line_break(""),
            self.ipv6_info,
            self.ipv6_method,
            Padding.line_break(""),
        ])
        return body

    def _set_ipv4_prefixes(self):
        if len(self.dev.configured_ip_addresses_for_version(4)) > 0:
            active = 0
        elif self.dev.dhcp4:
            active = 1
        else:
            active = 2
        for i in range(len(self.ipv4_method.contents)):
            b = self.ipv4_method[i]
            if i == active:
                p = "(*) "
            else:
                p = "( ) "
            b.set_label(p + b.label[4:])

    def _set_ipv6_prefixes(self):
        if len(self.dev.configured_ip_addresses_for_version(6)) > 0:
            active = 0
        elif self.dev.dhcp6:
            active = 1
        else:
            active = 2
        for i in range(len(self.ipv6_method.contents)):
            b = self.ipv6_method[i]
            if i == active:
                p = "(*) "
            else:
                p = "( ) "
            b.set_label(p + b.label[4:])

    def _build_ipv4_method_buttons(self):
        button_padding = 70

        buttons = [
            menu_btn(label="    %s" % _("Use a static IPv4 configuration"),
                    on_press=self.show_ipv4_configuration),
            choice_btn(label="    %s" % _("Use DHCPv4 on this interface"),
                    on_press=self.enable_dhcp4),
            choice_btn(label="    %s" % _("Do not use"),
                    on_press=self.clear_ipv4),
        ]
        for btn in buttons:
            btn.original_widget._label._cursor_position = 1
        padding = getattr(Padding, 'left_{}'.format(button_padding))
        buttons = [ padding(button) for button in buttons ]

        return buttons

    def _build_ipv6_method_buttons(self):
        button_padding = 70

        buttons = [
            menu_btn(label="    %s" % _("Use a static IPv6 configuration"),
                    on_press=self.show_ipv6_configuration),
            choice_btn(label="    %s" % _("Use DHCPv6 on this interface"),
                    on_press=self.enable_dhcp6),
            choice_btn(label="    %s" % _("Do not use"),
                    on_press=self.clear_ipv6),
        ]

        for btn in buttons:
            btn.original_widget._label._cursor_position = 1

        padding = getattr(Padding, 'left_{}'.format(button_padding))
        buttons = [ padding(button) for button in buttons ]

        return buttons


    def _build_wifi_config(self):
        btn = menu_btn(label=_("Configure WIFI settings"), on_press=self.show_wlan_configuration)
        return [Padding.left_70(btn)]

    def _build_buttons(self):
        buttons = [
            done_btn(_("Done"), on_press=self.done)
        ]
        return button_pile(buttons)

    def refresh_model_inputs(self):
        try:
            self.dev = self.model.get_netdev_by_name(self.dev.name)
        except KeyError:
            # The interface is gone
            self.controller.default()
            return
        if self.dev.type == 'wlan':
            self.wifi_info.contents = [ (obj, ('pack', None)) for obj in _build_wifi_info(self.dev) ]
        self.ipv4_info.contents = [ (obj, ('pack', None)) for obj in _build_gateway_ip_info_for_version(self.dev, 4) ]
        self.ipv6_info.contents = [ (obj, ('pack', None)) for obj in _build_gateway_ip_info_for_version(self.dev, 6) ]

    def clear_ipv4(self, btn):
        self.dev.remove_ip_networks_for_version(4)
        self.dev.remove_nameservers()
        self.model.set_default_v4_gateway(None, None)
        self._set_ipv4_prefixes()
        self.refresh_model_inputs()

    def clear_ipv6(self, btn):
        self.dev.remove_ip_networks_for_version(6)
        self.dev.remove_nameservers()
        self.model.set_default_v6_gateway(None, None)
        self._set_ipv6_prefixes()
        self.refresh_model_inputs()

    def enable_dhcp4(self, btn):
        self.clear_ipv4(btn)
        self.dev.remove_nameservers()
        self.dev.dhcp4 = True
        self.refresh_model_inputs()
        self._set_ipv4_prefixes()

    def enable_dhcp6(self, btn):
        self.clear_ipv6(btn)
        self.dev.remove_nameservers()
        self.dev.dhcp6 = True
        self.refresh_model_inputs()
        self._set_ipv6_prefixes()

    def show_wlan_configuration(self, btn):
        self.controller.network_configure_wlan_interface(self.dev.name)

    def show_ipv4_configuration(self, btn):
        self.controller.network_configure_ipv4_interface(self.dev.name)

    def show_ipv6_configuration(self, btn):
        self.controller.network_configure_ipv6_interface(self.dev.name)

    def cancel(self):
        self.controller.default()

    def done(self, result):
        self.controller.default()
