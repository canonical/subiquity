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

from urwid import (
    LineBox,
    ProgressBar,
    Text,
    WidgetWrap,
    )

from subiquitycore.ui.buttons import cancel_btn, menu_btn, done_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
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

def _build_wifi_info(dev):
    r = []
    if dev.actual_ssid is not None:
        if dev.configured_ssid is not None:
            if dev.actual_ssid != dev.configured_ssid:
                r.append(Text("Associated to '%s', will associate to '%s'"%(dev.actual_ssid, dev.configured_ssid)))
            else:
                r.append(Text("Associated to '" + dev.actual_ssid + "'"))
        else:
            r.append(Text("No access point configured, but associated to '%s'"%(dev.actual_ssid,)))
    else:
        if dev.configured_ssid is not None:
            r.append(Text("Will associate to '" + dev.configured_ssid + "'"))
        else:
            r.append(Text("No access point configured"))
    return r

def _format_address_list(label, addresses):
    if len(addresses) == 0:
        return []
    elif len(addresses) == 1:
        return [Text(label%('',)+' '+str(addresses[0]))]
    else:
        ips = []
        for ip in addresses:
            ips.append(str(ip))
        return [Text(label%('es',) + ' ' + ', '.join(ips))]


def _build_gateway_ip_info_for_version(dev, version):
    actual_ip_addresses = dev.actual_ip_addresses_for_version(version)
    configured_ip_addresses = dev.configured_ip_addresses_for_version(version)
    if dev.dhcp_for_version(version):
        if dev.actual_ip_addresses:
            return _format_address_list("Will use DHCP for IPv%s, currently has address%%s:"%(version,), actual_ip_addresses)
        return [Text("Will use DHCP for IPv%s"%(version,))]
    elif configured_ip_addresses:
        if sorted(actual_ip_addresses) == sorted(configured_ip_addresses):
            return _format_address_list("Using static address%%s for IPv%s:"%(version,), actual_ip_addresses)
        p = _format_address_list("Will use static address%%s for IPv%s:"%(version,), configured_ip_addresses)
        if actual_ip_addresses:
            p.extend(_format_address_list("Currently has address%s:", actual_ip_addresses))
        return p
    elif actual_ip_addresses:
        return _format_address_list("Has no IPv%s configuration, currently has address%%s:"%(version,), actual_ip_addresses)
    else:
        return [Text("IPv%s is not configured"%(version,))]


class NetworkView(BaseView):
    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.items = []
        self.error = Text("", align='center')
        self.model_inputs = Pile(self._build_model_inputs())
        self.additional_options = Pile(self._build_additional_options())
        self.body = [
            Padding.center_79(self.model_inputs),
            Padding.line_break(""),
            Padding.center_79(self.additional_options),
            Padding.line_break(""),
            Padding.center_79(Color.info_error(self.error)),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons()),
        ]
        # FIXME determine which UX widget should have focus
        self.lb = ListBox(self.body)
        self.lb.set_focus(4)  # _build_buttons
        super().__init__(self.lb)

    def _build_buttons(self):
        cancel = Color.button(cancel_btn(on_press=self.cancel))
        done = Color.button(done_btn(on_press=self.done))
        self.default_focus = done

        buttons = [done, cancel]
        return Pile(buttons, focus_item=done)

    def _build_model_inputs(self):
        netdevs = self.model.get_all_netdevs()
        ifname_width = 8  # default padding
        if netdevs:
            ifname_width += max(map(lambda dev: len(dev.name), netdevs))
            if ifname_width > 20:
                ifname_width = 20

        iface_menus = []

        # Display each interface -- name in first column, then configured IPs
        # in the second.
        log.debug('interfaces: {}'.format(netdevs))
        for dev in netdevs:
            col_1 = []
            col_2 = []

            col_1.append(
                Color.menu_button(
                    menu_btn(label=dev.name, on_press=self.on_net_dev_press)))

            if dev.type == 'wlan':
                col_2.extend(_build_wifi_info(dev))
            if len(dev.actual_ip_addresses) == 0 and dev.type == 'eth' and not dev.is_connected:
                col_2.append(Color.info_primary(Text("Not connected")))
            col_2.extend(_build_gateway_ip_info_for_version(dev, 4))
            col_2.extend(_build_gateway_ip_info_for_version(dev, 6))

            # Other device info (MAC, vendor/model, speed)
            template = ''
            if dev.hwaddr:
                template += '{} '.format(dev.hwaddr)
            if dev.is_bond_slave:
                template += '(Bonded) '
            if not dev.vendor.lower().startswith('unknown'):
                vendor = textwrap.wrap(dev.vendor, 15)[0]
                template += '{} '.format(vendor)
            if not dev.model.lower().startswith('unknown'):
                model = textwrap.wrap(dev.model, 20)[0]
                template += '{} '.format(model)
            if dev.speed:
                template += '({})'.format(dev.speed)

            col_2.append(Color.info_minor(Text(template)))
            iface_menus.append(Columns([(ifname_width, Pile(col_1)), Pile(col_2)], 2))

        return iface_menus

    def refresh_model_inputs(self):
        self.model_inputs.contents = [ (obj, ('pack', None)) for obj in self._build_model_inputs() ]
        self.additional_options.contents = [ (obj, ('pack', None)) for obj in self._build_additional_options() ]

    def _build_additional_options(self):
        labels = []
        netdevs = self.model.get_all_netdevs()

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
        for opt, sig in self.model.get_menu():
            if ':set-default-route' in sig:
                if len(netdevs) < 2:
                    log.debug('Skipping default route menu option'
                              ' (only one nic)')
                    continue
            if ':bond-interfaces' in sig:
                not_bonded = [dev for dev in netdevs if not dev.is_bonded]
                if len(not_bonded) < 2:
                    log.debug('Skipping bonding menu option'
                              ' (not enough available nics)')
                    continue

            if len(opt) > max_btn_len:
                max_btn_len = len(opt)

            buttons.append(
                Color.menu_button(
                    menu_btn(label=opt,
                             on_press=self.additional_menu_select,
                             user_data=sig)))

        from urwid import Padding
        buttons = [ Padding(button, align='left', width=max_btn_len + 6) for button in buttons ]
        return labels + buttons

    def additional_menu_select(self, result, sig):
        self.controller.signal.emit_signal(sig)

    def on_net_dev_press(self, result):
        log.debug("Selected network dev: {}".format(result.label))
        self.controller.network_configure_interface(result.label)

    def show_network_error(self, action, info=None):
        if action == 'generate':
            self.error.set_text("Network configuration failed: %r" % (info,))
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
        self.controller.network_finish(self.model.render())

    def cancel(self, button):
        self.controller.cancel()
