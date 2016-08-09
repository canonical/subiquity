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
from netifaces import AF_INET, AF_INET6
from subiquitycore.ui.lists import SimpleList
from subiquitycore.ui.buttons import cancel_btn, menu_btn, done_btn
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.view import BaseView


log = logging.getLogger('subiquitycore.views.network')


class NetworkView(BaseView):
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
        col_2 = []

        # Display each interface -- name in first column, then configured IPs
        # in the second.
        log.debug('interfaces: {}'.format(ifaces))
        for iface in ifaces:
            col_1.append(
                Color.info_major(
                    menu_btn(label=iface,
                             on_press=self.on_net_dev_press),
                    focus_map='button focus'))

            interface = self.model.get_interface(iface)
            ip_status = {
                'ip4': interface.ip4,
                'ip4_methods': interface.ip4_methods,
                'ip4_providers': interface.ip4_providers,
                'subnets': interface.subnets,
            }

            log.debug('{}: IPv4 addresses: {}'.format(iface, ip_status['ip4']))
            log.debug('{}: IPv4 methods: {}'.format(iface, ip_status['ip4_methods']))
            log.debug('{}: IPv4 providers: {}'.format(iface, ip_status['ip4_providers']))
            log.debug('{}: subnets: {}'.format(iface, ip_status['subnets']))
            #log.debug('{}: IPv6 subnets: {}'.format(iface, ip_status['ip6_subnets']))

            # Show IPv4 configuration.
            ipv4_template = ''
            if len(ip_status['subnets']) > 1:
                for subnet in ip_status['subnets']:
                    ipv4_template += '\t{address} ({type})\n'.format(**subnet)
                    col_1.append(Text(""))  # vertical holder for ipv4 status
            else:
                if len(ip_status['ip4']) == 0:
                    ipv4_template += "No IPv4 configuration"
                    col_1.append(Text(""))  # vertical holder for ipv4 status
                for i in range(len(ip_status['ip4'])):
                    col_1.append(Text(""))  # vertical holder for ipv4 status

                    if i > 0:
                        ipv4_template += '\n'

                    ipv4_template += '{}'.format(ip_status['ip4'][i])
                    try:
                        ipv4_template += ' ({}) '.format(ip_status['ip4_methods'][i])
                    except IndexError:
                        pass
            col_2.append(Color.info_primary(Text(ipv4_template)))

            # TODO: complete IPv6 displaying.
            col_1.append(Text(""))  # vertical holder for ipv6 status
            col_2.append(Color.info_primary(Text("No IPv6 configuration")))  # vert. holder for ipv6

            # Other device info (MAC, vendor/model, speed)
            info = self.model.get_iface_info(iface)
            hwaddr = self.model.get_hw_addr(iface)
            log.debug('iface info:{}'.format(info))
            template = ''
            if hwaddr:
                template += '{} '.format(hwaddr)
            if info['bond_slave']:
                template += '(Bonded) '
            if not info['vendor'].lower().startswith('unknown'):
                vendor = textwrap.wrap(info['vendor'], 15)[0]
                template += '{} '.format(vendor)
            if not info['model'].lower().startswith('unknown'):
                model = textwrap.wrap(info['model'], 20)[0]
                template += '{} '.format(model)
            if info['speed']:
                template += '({speed})'.format(**info)

            col_2.append(Color.info_minor(Text(template)))

        col_1 = BoxAdapter(SimpleList(col_1),
                           height=len(col_1))
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
            gateways = self.model.get_routes()
            # FIXME: maybe deal with the case there are no routes at all?
            ipv4_gateways = gateways['default'].get(AF_INET, [])
            ipv6_gateways = gateways['default'].get(AF_INET6, [])
            route_source = "is unset"
            if self.model.default_gateway is not None:
                route_source = "via " + self.model.default_gateway
            elif len(ipv4_gateways):
                route_source = ""
                if ipv4_gateways[0]:
                    route_source += "via {}".format(ipv4_gateways[0])
                elif ipv4_gateways[1]:
                    route_source += "through interface {}".format(ipv4_gateways[1])
            default_route_w = Color.info_minor(
                Text("  IPv4 default route " + route_source + "."))
            opts.append(default_route_w)

            # FIXME: do ipv6 default gateway
            # if ipv6:
            # if self.model.default_gateway6 is not None:
            route_source = "is unset"
            if len(ipv6_gateways):
                route_source = ""
                if ipv6_gateways[0]:
                    route_source += "via {}".format(ipv6_gateways[0])
                elif ipv6_gateways[1]:
                    route_source += "through interface {}".format(ipv6_gateways[1])
            default_route_w = Color.info_minor(
                Text("  IPv6 default route " + route_source + "."))
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
