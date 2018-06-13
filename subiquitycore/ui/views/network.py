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
from urwid import Padding as uPadding

from subiquitycore.ui.buttons import back_btn, cancel_btn, done_btn, menu_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.utils import button_pile, Color, Padding
from subiquitycore.view import BaseView


log = logging.getLogger('subiquitycore.views.network')


class ApplyingConfigWidget(WidgetWrap):

    def __init__(self, step_count, cancel_func):
        self.cancel_func = cancel_func
        button = cancel_btn(_("Cancel"), on_press=self.do_cancel)
        self.bar = ProgressBar(normal='progress_incomplete',
                               complete='progress_complete',
                               current=0, done=step_count)
        box = LineBox(Pile([self.bar,
                            button_pile([button])]),
                      title=_("Applying network config"))
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
                r.append(
                    Text(_("Associated to '%s', will "
                           "associate to '%s'" % (dev.actual_ssid,
                                                  dev.configured_ssid))))
            else:
                r.append(Text(_("Associated to '%s'" % dev.actual_ssid)))
        else:
            r.append(Text(_("No access point configured, but associated "
                            "to '%s'" % dev.actual_ssid)))
    else:
        if dev.configured_ssid is not None:
            r.append(Text(_("Will associate to '%s'" % dev.configured_ssid)))
        else:
            r.append(Text(_("No access point configured")))
    return r


def _format_address_list(label, addresses):
    if len(addresses) == 0:
        return []
    elif len(addresses) == 1:
        return [Text(label % ('',) + ' ' + str(addresses[0]))]
    else:
        ips = []
        for ip in addresses:
            ips.append(str(ip))
        return [Text(label % ('es',) + ' ' + ', '.join(ips))]


def _build_gateway_ip_info_for_version(dev, version):
    actual_ip_addresses = dev.actual_ip_addresses_for_version(version)
    configured_ip_addresses = dev.configured_ip_addresses_for_version(version)
    if dev.dhcp_for_version(version):
        if dev.actual_ip_addresses_for_version(version):
            return _format_address_list(_("Will use DHCP for IPv%s, currently "
                                          "has address%%s:" % version),
                                        actual_ip_addresses)
        return [Text(_("Will use DHCP for IPv%s" % version))]
    elif configured_ip_addresses:
        if sorted(actual_ip_addresses) == sorted(configured_ip_addresses):
            return _format_address_list(
                _("Using static address%%s for IPv%s:" % version),
                actual_ip_addresses)
        p = _format_address_list(
            _("Will use static address%%s for IPv%s:" % version),
            configured_ip_addresses)
        if actual_ip_addresses:
            p.extend(_format_address_list(_("Currently has address%s:"),
                                          actual_ip_addresses))
        return p
    elif actual_ip_addresses:
        return _format_address_list(_("Has no IPv%s configuration, currently "
                                      "has address%%s:" % version),
                                    actual_ip_addresses)
    else:
        return [Text(_("IPv%s is not configured" % version))]


class NetworkView(BaseView):
    title = _("Network connections")
    excerpt = _("Configure at least one interface this server can use to talk "
                "to other machines, and which preferably provides sufficient "
                "access for updates.")
    footer = _("Select an interface to configure it or select Done to "
               "continue")

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.items = []
        self.error = Text("", align='center')
        self.additional_options = Pile(self._build_additional_options())
        self.listbox = ListBox(self._build_model_inputs() + [
            Padding.center_79(self.additional_options),
            Padding.line_break(""),
        ])
        self.bottom = Pile([
                Text(""),
                self._build_buttons(),
                Text(""),
                ])
        self.error_showing = False
        self.frame = Pile([
            ('pack', Text("")),
            ('pack', Padding.center_79(Text(_(self.excerpt)))),
            ('pack', Text("")),
            Padding.center_90(self.listbox),
            ('pack', self.bottom)])
        self.frame.focus_position = 4
        super().__init__(self.frame)

    def _build_buttons(self):
        back = back_btn(_("Back"), on_press=self.cancel)
        done = done_btn(_("Done"), on_press=self.done)
        return button_pile([done, back])

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
                    menu_btn(label=dev.name, on_press=self.on_net_dev_press))

            if dev.type == 'wlan':
                col_2.extend(_build_wifi_info(dev))
            if len(dev.actual_ip_addresses) == 0 and (
                    dev.type == 'eth' and not dev.is_connected):
                col_2.append(Color.info_primary(Text(_("Not connected"))))
            col_2.extend(_build_gateway_ip_info_for_version(dev, 4))
            col_2.extend(_build_gateway_ip_info_for_version(dev, 6))

            # Other device info (MAC, vendor/model, speed)
            template = ''
            if dev.hwaddr:
                template += '{} '.format(dev.hwaddr)
            # TODO is this to translate?
            if dev.is_bond_slave:
                template += '(Bonded) '
            # TODO to check if this is affected by translations
            if not dev.vendor.lower().startswith('unknown'):
                vendor = textwrap.wrap(dev.vendor, 15)[0]
                template += '{} '.format(vendor)
            if not dev.model.lower().startswith('unknown'):
                model = textwrap.wrap(dev.model, 20)[0]
                template += '{} '.format(model)
            if dev.speed:
                template += '({})'.format(dev.speed)

            col_2.append(Color.info_minor(Text(template)))
            iface_menus.append(
                Columns([(ifname_width, Pile(col_1)), Pile(col_2)], 2))

        return iface_menus

    def refresh_model_inputs(self):
        widgets = self._build_model_inputs() + [
            Padding.center_79(self.additional_options),
            Padding.line_break(""),
        ]
        self.listbox.base_widget.body[:] = widgets
        self.additional_options.contents = [
            (obj, ('pack', None)) for obj in self._build_additional_options()]

    def _build_additional_options(self):
        labels = []
        netdevs = self.model.get_all_netdevs()

        # Display default route status
        if self.model.default_v4_gateway is not None:
            v4_route_source = "via " + self.model.default_v4_gateway

            default_v4_route_w = Color.info_minor(
                Text(_("  IPv4 default route %s." % v4_route_source)))
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
                menu_btn(
                    label=opt,
                    on_press=self.additional_menu_select,
                    user_data=sig))

        buttons = [uPadding(button, align='left', width=max_btn_len + 6)
                   for button in buttons]
        r = labels + buttons
        if len(r) > 0:
            r[0:0] = [Text("")]
        return r

    def additional_menu_select(self, result, sig):
        self.controller.signal.emit_signal(sig)

    def on_net_dev_press(self, result):
        log.debug("Selected network dev: {}".format(result.label))
        self.controller.network_configure_interface(result.label)

    def show_network_error(self, action, info=None):
        self.error_showing = True
        self.bottom.contents[0:0] = [
            (Text(""), self.bottom.options()),
            (Color.info_error(self.error), self.bottom.options()),
            ]
        if action == 'stop-networkd':
            exc = info[0]
            self.error.set_text(
                "Stopping systemd-networkd-failed: %r" % (exc.stderr,))
        elif action == 'apply':
            self.error.set_text("Network configuration could not be applied; "
                                "please verify your settings.")
        elif action == 'timeout':
            self.error.set_text("Network configuration timed out; "
                                "please verify your settings.")
        elif action == 'down':
            self.error.set_text("Downing network interfaces failed.")
        elif action == 'canceled':
            self.error.set_text("Network configuration canceled.")
        else:
            self.error.set_text("An unexpected error has occurred; "
                                "please verify your settings.")

    def done(self, result):
        if self.error_showing:
            self.bottom.contents[0:2] = []
        self.controller.network_finish(self.model.render())

    def cancel(self, button=None):
        self.controller.cancel()
