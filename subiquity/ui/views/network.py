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

""" Network Model

Provides network device listings and extended network information

"""

import logging
from urwid import (ListBox, Pile, BoxAdapter,
                   Text, Columns)
from subiquity.ui.lists import SimpleList
from subiquity.ui.buttons import cancel_btn, menu_btn
from subiquity.ui.utils import Padding, Color
from subiquity.view import ViewPolicy


log = logging.getLogger('subiquity.network')


class NetworkView(ViewPolicy):
    def __init__(self, model, signal):
        self.model = model
        self.signal = signal
        self.items = []
        self.body = [
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_79(self._build_additional_options()),
            Padding.line_break(""),
            Padding.center_15(self._build_buttons()),
        ]
        super().__init__(ListBox(self.body))

    def _build_buttons(self):
        buttons = [
            Color.button(cancel_btn(on_press=self.cancel),
                         focus_map='button focus'),
        ]
        return Pile(buttons)

    def _build_model_inputs(self):
        log.info("probing for network devices")
        self.model.probe_network()
        ifaces = self.model.get_interfaces()

        col_1 = []
        for iface in ifaces:
            col_1.append(
                Color.menu_button(
                    menu_btn(label=iface,
                             on_press=self.on_net_dev_press),
                    focus_map='menu_button focus'))
            col_1.append(Text(""))  # vertical holder for ipv6 status
            col_1.append(Text(""))  # vertical holder for ipv4 status
        col_1 = BoxAdapter(SimpleList(col_1),
                           height=len(col_1))

        col_2 = []
        for iface in ifaces:
            ifinfo, iface_vendor, iface_model = self.model.get_iface_info(
                iface)
            bonded = self.model.iface_is_bonded(iface)
            bridged = self.model.iface_is_bridge_member(iface)
            speed = self.model.iface_get_speed(iface)
            info = {
                'bonded': bonded,
                'bridged': bridged,
                'speed': speed,
                'vendor': iface_vendor,
                'model': iface_model,
            }
            template = ''
            if info['bonded']:
                template += '(Bonded) '
            if info['speed']:
                template += '{speed} '.format(**info)
            if not info['vendor'].lower().startswith('unknown'):
                template += '{vendor} '.format(**info)
            if not info['model'].lower().startswith('unknown'):
                template += '{model} '.format(**info)
            col_2.append(Text(template))

            ip = ifinfo.addr
            method = self.model.iface_get_ip_method(iface)
            provider = self.model.iface_get_ip_provider(iface)
            ipv4_status = {
                'ip': ip,
                'method': method,
                'provider': provider,
            }
            ipv4_template = ''
            if ipv4_status['ip']:
                ipv4_template += '{ip} '.format(**ipv4_status)
            if ipv4_status['method']:
                ipv4_template += 'provided by {method} '.format(**ipv4_status)
            if ipv4_status['provider']:
                ipv4_template += 'from {provider} '.format(**ipv4_status)
            col_2.append(Text(ipv4_template))
            col_2.append(Text("Checking IPv6..."))  # vertical holder for ipv6
        if len(col_2):
            col_2 = BoxAdapter(SimpleList(col_2, is_selectable=False),
                               height=len(col_2))
        else:
            col_2 = Pile([Text("No network interfaces detected.")])

        return Columns([(10, col_1), col_2], 2)

    def _build_additional_options(self):
        opts = []
        for opt, sig, _ in self.model.get_menu():
            opts.append(
                Color.menu_button(
                    menu_btn(label=opt,
                             on_press=self.additional_menu_select),
                    focus_map='menu_button focus'))
        return Pile(opts)

    def additional_menu_select(self, result):
        self.signal.emit_signal(self.model.get_signal_by_name(result.label))

    def on_net_dev_press(self, result):
        log.debug("Selected network dev: {}".format(result.label))
        self.signal.emit_signal('filesystem:show')

    def cancel(self, button):
        self.signal.emit_signal(self.model.get_previous_signal)
