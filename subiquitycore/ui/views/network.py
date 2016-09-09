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

from urwid import (ListBox, Pile,
                   Text, Columns, Overlay,
                   LineBox, ProgressBar, WidgetWrap)

from subiquitycore.ui.buttons import cancel_btn, menu_btn, done_btn
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.view import BaseView


log = logging.getLogger('subiquitycore.views.network')


class ApplyingConfigWidget(WidgetWrap):

    def __init__(self, step_count, cancel_func):
        self.cancel_func = cancel_func
        button = cancel_btn(on_press=self.do_cancel)
        self.bar = ProgressBar(normal='progress_incomplete',
                        complete='progress_complete',
                        current=0, done=step_count)
        box = LineBox(Pile([self.bar,
                            Padding.fixed_10(button)]),
                      title="Applying network config")
        super().__init__(box)

    def advance(self):
        self.bar.current += 1

    def do_cancel(self, sender):
        self.cancel_func()


class NetworkView(BaseView):
    def __init__(self, model, signal):
        self.model = model
        self.signal = signal
        self.items = []
        self.error = Text("", align='center')
        self.body = [
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_79(self._build_additional_options()),
            Padding.line_break(""),
            Padding.center_79(Color.info_error(self.error)),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons()),
        ]
        # FIXME determine which UX widget should have focus
        self.lb = ListBox(self.body)
        self.lb.set_focus(4)  # _build_buttons
        super().__init__(self.lb)

    def show_overlay(self, overlay_widget):
        self.orig_w = self._w
        self._w = Overlay(top_w=overlay_widget,
                          bottom_w=self._w,
                          align='center',
                          width=('relative', 60),
                          min_width=80,
                          valign='middle',
                          height='pack')

    def remove_overlay(self, overlay_widget):
        # urwid note: we could also get orig_w as
        # self._w.contents[0][0], but this is clearer:
        self._w = self.orig_w

    def _build_buttons(self):
        cancel = Color.button(cancel_btn(on_press=self.cancel),
                              focus_map='button focus')
        done = Color.button(done_btn(on_press=self.done),
                            focus_map='button focus')
        self.default_focus = done

        buttons = [done, cancel]
        return Pile(buttons, focus_item=done)

    def _build_model_inputs(self):
        ifaces = self.model.get_all_interface_names()
        ifname_width = 8  # default padding
        if ifaces:
            ifname_width += len(max(ifaces, key=len))
            if ifname_width > 20:
                ifname_width = 20

        iface_menus = []
        
        # Display each interface -- name in first column, then configured IPs
        # in the second.
        log.debug('interfaces: {}'.format(ifaces))
        for iface in ifaces:
            col_1 = []
            col_2 = []

            col_1.append(
                Color.info_major(
                    menu_btn(label=iface,
                             on_press=self.on_net_dev_press),
                    focus_map='button focus'))

            interface = self.model.get_interface(iface)
            ip_status = {
                'ipv4_addresses': interface.ipv4_addresses,
                'ipv6_addresses': interface.ipv6_addresses,
                'dhcp4_addresses': interface.dhcp4_addresses,
                'dhcp6_addresses': interface.dhcp6_addresses,
                'dhcp4': interface.dhcp4,
                'dhcp6': interface.dhcp6,
            }

            for addr in ip_status['dhcp4_addresses']:
                template = '{} (dhcp)'.format(addr[0])
                col_1.append(Text("")) 
                col_2.append(Color.info_primary(Text(template)))

            for addr in ip_status['ipv4_addresses']:
                template = '{} (manual)'.format(addr)
                col_1.append(Text("")) 
                col_2.append(Color.info_primary(Text(template)))

            for addr in ip_status['dhcp6_addresses']:
                template = '{} (dhcp)'.format(addr[0])
                col_1.append(Text("")) 
                col_2.append(Color.info_primary(Text(template)))

            for addr in ip_status['ipv6_addresses']:
                template = '{} (manual)'.format(addr)
                col_1.append(Text("")) 
                col_2.append(Color.info_primary(Text(template)))

            template = None
            if ( not ip_status['dhcp4'] and not ip_status['dhcp6'] ) \
                    and len(ip_status['ipv4_addresses']) == 0 and \
                    len(ip_status['ipv6_addresses']) == 0:
                template = "Not configured"

            if ip_status['dhcp4'] and ip_status['dhcp6'] and \
                    len(ip_status['ipv4_addresses']) == 0 and \
                    len(ip_status['dhcp4_addresses']) == 0 and \
                    len(ip_status['ipv6_addresses']) == 0 and \
                    len(ip_status['dhcp6_addresses']) == 0:
                template = "DHCP is enabled"
            elif ip_status['dhcp4'] and \
                    len(ip_status['ipv4_addresses']) == 0 and \
                    len(ip_status['dhcp4_addresses']) == 0:
                template = "DHCPv4 is enabled"
            elif ip_status['dhcp6'] and \
                    len(ip_status['ipv6_addresses']) == 0 and \
                    len(ip_status['dhcp6_addresses']) == 0:
                template = "DHCPv6 is enabled"

            if template is not None:
                col_1.append(Text("")) 
                col_2.append(Color.info_primary(Text(template)))

            if interface.iftype == 'wlan':
                if interface.essid is not None:
                    col_2.append(Text("Associated to '" + interface.essid + "'"))
                else:
                    col_2.append(Text("Not associated."))

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
            #log.debug('template: {}', template)
            log.debug('hwaddr:{}, {}'.format(hwaddr, template))

            col_2.append(Color.info_minor(Text(template)))
            iface_menus.append(Columns([(ifname_width, Pile(col_1)), Pile(col_2)], 2))

        return Pile(iface_menus)

    def _build_additional_options(self):
        labels = []
        ifaces = self.model.get_all_interface_names()

        # Display default route status
        if self.model.default_v4_gateway is not None:
            v4_route_source = "via " + self.model.default_v4_gateway

            default_v4_route_w = Color.info_minor(
                Text("  IPv4 default route " + v4_route_source + "."))
            labels.append(default_v4_route_w)
            
        if self.model.default_v6_gateway is not None:
            v6_route_source = "via " + self.model.default_v6_gateway

            default_v6_route_w = Color.info_minor(
                Text("  IPv6 default route " + v6_route_source + "."))
            labels.append(default_v6_route_w)

        max_btn_len = 0
        buttons = []
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

            if len(opt) > max_btn_len:
                max_btn_len = len(opt)

            buttons.append(
                Color.menu_button(
                    menu_btn(label=opt,
                             on_press=self.additional_menu_select),
                    focus_map='button focus'))

        padding = getattr(Padding, 'left_{}'.format(max_btn_len + 10))
        buttons = [ padding(button) for button in buttons ]
        return Pile(labels + buttons)

    def additional_menu_select(self, result):
        self.signal.emit_signal(self.model.get_signal_by_name(result.label))

    def on_net_dev_press(self, result):
        log.debug("Selected network dev: {}".format(result.label))
        self.signal.emit_signal('menu:network:main:configure-interface',
                                result.label)

    def show_network_error(self, action):
        if action == 'generate':
            self.error.set_text("Network configuration failed; " + \
                                "please verify your settings.")
        elif action == 'apply':
            self.error.set_text("Network configuration could not be applied; " + \
                                "please verify your settings.")
        elif action == 'timeout':
            self.error.set_text("Network configuration timed out; " + \
                                "please verify your settings.")
        elif action == 'canceled':
            self.error.set_text("Network configuration canceled.")
        else:
            self.error.set_text("An unexpected error has occurred; " + \
                                "please verify your settings.")

    def done(self, result):
        self.signal.emit_signal('network:finish', self.model.render())

    def cancel(self, button):
        # Because of the double signal hack done in the controller we
        # need to pop two signals here.
        self.signal.signal_stack.pop()
        self.signal.prev_signal()
