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
import socket

from urwid import Text

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import cancel_btn, done_btn, menu_btn
from subiquitycore.ui.container import ListBox, Pile
from subiquitycore.ui.utils import Color, Padding
from subiquitycore.ui.interactive import StringEditor

log = logging.getLogger('subiquitycore.network.set_default_route')


class NetworkSetDefaultRouteView(BaseView):
    def __init__(self, model, family, controller):
        self.model = model
        self.family = family
        self.controller = controller
        self.default_gateway_w = None
        self.gateway_options = Pile(self._build_default_routes())
        body = [
            Padding.center_79(Text("Please set the default gateway:")),
            Padding.line_break(""),
            Padding.center_79(self.gateway_options),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        super().__init__(ListBox(body))

    def _build_default_routes(self):
        ''' iterate through interfaces collecting
            any uniq provider (aka, gateway) and
            associate the interface name with the gateway

            then generate a line per key in the gateway
            dict and display the keys.

            Upon selection of the gateway entry (ip)
            then we set model.set_default_gateway(ip)

            if manual is selected, then we update
            the second entry into a IPAddressEditor
            and accept the value, submitting it to
            the model.
        '''
        providers = {}

        for iface in self.model.get_all_interfaces():
            if self.family == socket.AF_INET:
                ip_providers = iface.ip4_providers
            elif self.family == socket.AF_INET6:
                ip_providers = iface.ip6_providers

            for provider in ip_providers:
                log.debug('ipv4 provider: {}'.format(provider))
                gw = provider
                if gw in providers:
                    providers[gw].append(iface.ifname)
                else:
                    providers[gw] = [iface.ifname]

        log.debug('gateway providers: {}'.format(providers))
        items = []
        items.append(Padding.center_79(
            Color.menu_button(menu_btn(label="None", on_press=self.done))))
        for (gw, ifaces) in providers.items():
            if gw is None:
                continue
            items.append(Padding.center_79(
                Color.menu_button(menu_btn(
                    label="{gw} ({ifaces})".format(
                        gw=gw,
                        ifaces=(",".join(ifaces))),
                    on_press=self.done))))

        items.append(Padding.center_79(
            Color.menu_button(
                menu_btn(label="Specify the default route manually",
                         on_press=self.show_edit_default_route))))
        return items

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done),
            Color.button(cancel)
        ]
        return Pile(buttons)

    def show_edit_default_route(self, btn):
        log.debug("Re-rendering specify default route")
        self.default_gateway_w = StringEditor(
            caption="Default gateway will be ")
        self.gateway_options.contents[-1] = (
            Padding.center_50(Color.string_input(self.default_gateway_w)),
            self.gateway_options.options())

    def done(self, result):
        log.debug("changing default gw: {}".format(result))

        gw_func = None
        if self.family == socket.AF_INET:
            gw_func = self.model.set_default_v4_gateway
        elif self.family == socket.AF_INET6:
            gw_func = self.model.set_default_v6_gateway

        if self.default_gateway_w and self.default_gateway_w.value:
            try:
                gw_func(None, self.default_gateway_w.value)
            except ValueError:
                # FIXME: raise UX error message
                self.default_gateway_w.edit_text = ""
        else:
            gw_ip_from_label = result.label.split(" ")[0]
            log.debug("default gw entered: {}".format(gw_ip_from_label))
            try:
                if gw_ip_from_label.startswith('None'):
                    gw_func(None, None)
                else:
                    gw_func(None, gw_ip_from_label)
            except ValueError:
                # FIXME: raise UX error message
                pass
        self.controller.prev_view()

    def cancel(self, button):
        self.controller.prev_view()
