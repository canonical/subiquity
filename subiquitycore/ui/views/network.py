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
from socket import AF_INET, AF_INET6

from urwid import (
    connect_signal,
    LineBox,
    ProgressBar,
    Text,
    )

from subiquitycore.ui.actionmenu import ActionMenu
from subiquitycore.ui.buttons import (
    back_btn,
    cancel_btn,
    done_btn,
    menu_btn,
    )
from subiquitycore.ui.container import (
    ListBox,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.form import Toggleable
from subiquitycore.ui.stretchy import StretchyOverlay
from subiquitycore.ui.table import ColSpec, TablePile, TableRow
from subiquitycore.ui.utils import (
    button_pile,
    Color,
    make_action_menu_row,
    Padding,
    )
from .network_configure_manual_interface import (
    AddBondStretchy,
    AddVlanStretchy,
    EditNetworkStretchy,
    ViewInterfaceInfo,
    )
from .network_configure_wlan_interface import NetworkConfigureWLANStretchy

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
        self.device_table = TablePile(
            self._build_model_inputs(),
            spacing=2, colspecs={
                0: ColSpec(rpad=1),
                4: ColSpec(can_shrink=True, rpad=1),
                })
        self.listbox = ListBox([self.device_table] + [
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

    def _action_info(self, device):
        self.show_stretchy_overlay(ViewInterfaceInfo(self, device))

    def _action_edit_ipv4(self, device):
        self.show_stretchy_overlay(EditNetworkStretchy(self, device, 4))

    def _action_edit_wlan(self, device):
        self.show_stretchy_overlay(NetworkConfigureWLANStretchy(self, device))

    def _action_edit_ipv6(self, device):
        self.show_stretchy_overlay(EditNetworkStretchy(self, device, 6))

    def _action_add_vlan(self, device):
        self.show_stretchy_overlay(AddVlanStretchy(self, device))

    def _action_add_bond(self, device):
        self.show_stretchy_overlay(AddBondStretchy(self, device))

    def _action_add_master(self, device, master=None):
        self.controller.add_master(device, master)

    def _action_rm_dev(self, device):
        self.controller.rm_virtual_interface(device)

    def _action(self, sender, action, device):
        if isinstance(action, str):
            m = getattr(self, '_action_{}'.format(action))
            m(device)
        if isinstance(action, dict):
            action_name = action.pop('action')
            m = getattr(self, '_action_{}'.format(action_name))
            m(device, **action)

    def _build_model_inputs(self):
        netdevs = self.model.get_all_netdevs()
        masters = []
        for master in netdevs:
            if not master._net_info.bond['is_master']:
                continue
            masters.append((
                _("Set master to %s") % master.name,
                True,
                {'action': 'add_master', 'master': master},
                False))
        rows = []
        rows.append(TableRow([
            Color.info_minor(Text(header))
            for header in ["", "NAME", "TYPE", "DHCP", "ADDRESSES", ""]]))
        for dev in netdevs:
            dhcp = []
            if dev.dhcp4:
                dhcp.append('v4')
            if dev.dhcp6:
                dhcp.append('v6')
            if dhcp:
                dhcp = ",".join(dhcp)
            else:
                dhcp = '-'
            addresses = []
            for v in 4, 6:
                if dev.configured_ip_addresses_for_version(v):
                    addresses.extend([
                        "{} (static)".format(a)
                        for a in dev.configured_ip_addresses_for_version(v)
                        ])
                elif dev.dhcp_for_version(v):
                    if v == 4:
                        fam = AF_INET
                    elif v == 6:
                        fam = AF_INET6
                    for a in dev._net_info.addresses.values():
                        log.debug("a %s", a.serialize())
                        if a.family == fam and a.source == 'dhcp':
                            addresses.append("{} (from dhcp)".format(
                                a.address))
            if addresses:
                addresses = ", ".join(addresses)
            else:
                addresses = '-'
            actions = [
                ("Info", True, 'info', True),
            ]
            if dev.type == "wlan":
                actions.append(("Edit WiFi", True, "edit_wlan", True))
            actions += [
                ("Edit IPv4", True, 'edit_ipv4', True),
                ("Edit IPv6", True, 'edit_ipv6', True),
                ]
            if dev.type != 'vlan' and not dev._net_info.bond['is_slave']:
                actions.append((_("Add a VLAN tag"), True, 'add_vlan', True))
            if dev.is_virtual:
                actions.append((_("Delete"), True, 'rm_dev', True))
            else:
                if dev._net_info.bond['is_slave']:
                    actions.append((
                        _("Remove master"),
                        True,
                        {'action': 'add_master', 'master': None},
                        False))
                else:
                    actions.extend(masters)
                    actions.append((_("Create a new bond"), True, 'add_bond', True))
            menu = ActionMenu(actions)
            connect_signal(menu, 'action', self._action, dev)
            rows.append(make_action_menu_row([
                Text("["),
                Text(dev.name),
                Text(dev.type),
                Text(dhcp),
                Text(addresses, wrap='clip'),
                menu,
                Text("]"),
                ], menu))
            info = " / ".join([dev.hwaddr, dev.vendor, dev.model])
            rows.append(Color.info_minor(TableRow([
                Text(""),
                (4, Text(info)),
                Text("")])))
            rows.append(Color.info_minor(TableRow([(4, Text(""))])))
        return rows

    def refresh_model_inputs(self):
        self.device_table.set_contents(self._build_model_inputs())
        if isinstance(self._w, StretchyOverlay) and \
           hasattr(self._w.stretchy, 'refresh_model_inputs'):
            self._w.stretchy.refresh_model_inputs()
        # we have heading, and then three lines per interface
        # selectable line, extra line, whitespace line
        # and focus ends up on the last whitespace line
        # despite it, not being selectable. *derp*
        current_focus = self.device_table.focus_position
        if not self.device_table._w.contents[current_focus][0].selectable():
            if self.device_table._w.contents[current_focus-2][0].selectable():
                self.device_table._w.set_focus(current_focus-2)

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
        elif action == 'add-vlan':
            self.error.set_text("Failed to add a VLAN tag.")
        elif action == 'rm-dev':
            self.error.set_text("Failed to delete a virtual interface.")
        else:
            self.error.set_text("An unexpected error has occurred; "
                                "please verify your settings.")

    def done(self, result):
        if self.error_showing:
            self.bottom.contents[0:2] = []
        self.controller.network_finish(self.model.render())

    def cancel(self, button=None):
        self.controller.cancel()
