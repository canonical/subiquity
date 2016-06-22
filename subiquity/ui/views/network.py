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
import textwrap
from urwid import (ListBox, Pile, BoxAdapter,
                   Text, Columns)
import yaml
from subiquity.ui.lists import SimpleList
from subiquity.ui.buttons import cancel_btn, menu_btn, done_btn
from subiquity.ui.utils import Padding, Color
from subiquity.view import ViewPolicy


log = logging.getLogger('subiquity.views.network')


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
            Padding.fixed_10(self._build_buttons()),
        ]
        # FIXME determine which UX widget should have focus
        self.lb = ListBox(self.body)
        self.lb.set_focus(4)  # _build_buttons
        super().__init__(self.lb)
        

    def _build_buttons(self):
        cancel = Color.button(cancel_btn(on_press=self.cancel),
                              focus_map='button focus')
        done = Color.button(done_btn(on_press=self.done),
                            focus_map='button focus')
        self.default_focus = done

        buttons = [done, cancel]
        return Pile(buttons, focus_item=done)

    def _build_model_inputs(self):
        log.info("probing for network devices")
        self.model.probe_network()
        ifaces = self.model.get_all_interface_names()
        ifname_width = 8  # default padding

        col_1 = []
        for iface in ifaces:
            col_1.append(
                Color.menu_button(
                    menu_btn(label=iface,
                             on_press=self.on_net_dev_press),
                    focus_map='button focus'))
            col_1.append(Text(""))  # vertical holder for ipv6 status
            col_1.append(Text(""))  # vertical holder for ipv4 status
        col_1 = BoxAdapter(SimpleList(col_1),
                           height=len(col_1))

        col_2 = []
        for iface in ifaces:
            info = self.model.get_iface_info(iface)
            log.debug('iface info:{}'.format(info))
            template = ''
            if info['bond_slave']:
                template += '(Bonded) '
            if info['speed']:
                template += '{speed} '.format(**info)
            if not info['vendor'].lower().startswith('unknown'):
                vendor = textwrap.wrap(info['vendor'], 15)[0]
                template += '{} '.format(vendor)
            if not info['model'].lower().startswith('unknown'):
                model = textwrap.wrap(info['model'], 20)[0]
                template += '{} '.format(model)
            col_2.append(Text(template))

            interface = self.model.get_interface(iface)
            ipv4_status = {
                'ip': interface.ip,
                'method': interface.ip_method,
                'provider': interface.ip_provider,
            }
            log.debug('ipv4_status: {}'.format(ipv4_status))
            ipv4_template = ''
            if ipv4_status['ip']:
                ipv4_template += '{ip} '.format(**ipv4_status)
            if ipv4_status['method']:
                ipv4_template += 'provided by {method} '.format(**ipv4_status)
            if ipv4_status['provider']:
                ipv4_template += 'from {provider} '.format(**ipv4_status)
            col_2.append(Text(ipv4_template))
            col_2.append(Text("No IPv6 connection"))  # vert. holder for ipv6

        if len(col_2):
            col_2 = BoxAdapter(SimpleList(col_2, is_selectable=False),
                               height=len(col_2))
            ifname_width += len(max(ifaces, key=len))
            if ifname_width > 20:
                ifname_width = 20 
        else:
            col_2 = Pile([Text("No network interfaces detected.")])

        return Columns([(ifname_width, col_1), col_2], 2)

    def _build_additional_options(self):
        opts = []
        ifaces = self.model.get_all_interface_names()

        # Display default route status
        if len(ifaces) > 0:
            default_route = ("Default route is ")
            route_source = ("whatever DHCP provides on any interface")
            if self.model.default_gateway is not None:
                route_source = self.model.default_gateway
            default_route_w = Color.info_minor(
                Text("  " + default_route + route_source))
            opts.append(default_route_w)

        for opt, sig, _ in self.model.get_menu():
            if ':set-default-route' in sig:
                if len(ifaces) < 2:
                    log.debug('Skipping default route menu option'
                              ' (only one nic)')
                    continue
            if ':bond-interfaces' in sig:
                not_bonded = [iface for iface in ifaces
                              if not self.model.iface_is_bonded(iface)]
                if len(not_bonded) < 2:
                    log.debug('Skipping bonding menu option'
                              ' (not enough available nics)')
                    continue
            opts.append(
                Color.menu_button(
                    menu_btn(label=opt,
                             on_press=self.additional_menu_select),
                    focus_map='button focus'))
        return Pile(opts)

    def additional_menu_select(self, result):
        self.signal.emit_signal(self.model.get_signal_by_name(result.label))

    def on_net_dev_press(self, result):
        log.debug("Selected network dev: {}".format(result.label))
        self.signal.emit_signal('menu:network:main:configure-interface',
                                result.label)

    def done(self, result):
        actions = [iface.action.get() for iface in
                   self.model.get_configured_interfaces()]
        actions += self.model.get_default_route()
        log.debug('Configured Network Actions:\n{}'.format(
            yaml.dump(actions, default_flow_style=False)))
        self.signal.emit_signal('network:finish', actions)

    def cancel(self, button):
        self.model.reset()
        self.signal.prev_signal()
