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

from subiquitycore.models.network import (
    addr_version,
    NetDevAction,
    )
from subiquitycore.ui.actionmenu import ActionMenu
from subiquitycore.ui.buttons import (
    back_btn,
    cancel_btn,
    done_btn,
    menu_btn,
    )
from subiquitycore.ui.container import (
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.stretchy import StretchyOverlay
from subiquitycore.ui.table import ColSpec, TablePile, TableRow
from subiquitycore.ui.utils import (
    button_pile,
    Color,
    make_action_menu_row,
    screen,
    )
from .network_configure_manual_interface import (
    AddVlanStretchy,
    BondStretchy,
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


def _stretchy_shower(cls, *args):
    def impl(self, device):
        self.show_stretchy_overlay(cls(self, device, *args))
    impl.opens_dialog = True
    return impl


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
        self.dev_to_row = {}
        self.cur_netdevs = []
        self.error = Text("", align='center')
        self.device_table = TablePile(
            self._build_model_inputs(),
            spacing=2, colspecs={
                0: ColSpec(rpad=1),
                4: ColSpec(can_shrink=True, rpad=1),
                })

        self._create_bond_btn = menu_btn(
            _("Create bond"), on_press=self._create_bond)
        bp = button_pile([self._create_bond_btn])
        bp.align = 'left'

        rows = [
            self.device_table,
            bp,
        ]

        buttons = button_pile([
                    done_btn(_("Done"), on_press=self.done),
                    back_btn(_("Back"), on_press=self.cancel),
                    ])
        self.bottom = Pile([
            ('pack', buttons),
        ])

        self.error_showing = False

        super().__init__(screen(
            rows=rows,
            buttons=self.bottom,
            focus_buttons=True,
            excerpt=self.excerpt))

    def _build_buttons(self):
        back = back_btn(_("Back"), on_press=self.cancel)
        done = done_btn(_("Done"), on_press=self.done)
        return button_pile([done, back])

    _action_INFO = _stretchy_shower(ViewInterfaceInfo)
    _action_EDIT_WLAN = _stretchy_shower(NetworkConfigureWLANStretchy)
    _action_EDIT_IPV4 = _stretchy_shower(EditNetworkStretchy, 4)
    _action_EDIT_IPV6 = _stretchy_shower(EditNetworkStretchy, 6)
    _action_EDIT_BOND = _stretchy_shower(BondStretchy)
    _action_ADD_VLAN = _stretchy_shower(AddVlanStretchy)

    def _action_DELETE(self, device):
        touched_devs = set()
        if device.type == "bond":
            for name in device.config['interfaces']:
                touched_devs.add(self.model.get_netdev_by_name(name))
        device.config = None
        self.del_link(device)
        for dev in touched_devs:
            self.update_link(dev)

    def _action(self, sender, action, device):
        action, meth = action
        log.debug("_action %s %s", action.name, device.name)
        meth(device)

    def _cells_for_device(self, dev):
        notes = []
        for dev2 in self.model.get_all_netdevs():
            if dev2.type != "bond":
                continue
            if dev.name in dev2.config.get('interfaces', []):
                notes.append(_("enslaved to {}").format(dev2.name))
                break
        for v in 4, 6:
            configured_ip_addresses = []
            for ip in dev.config.get('addresses', []):
                if addr_version(ip) == v:
                    configured_ip_addresses.append(ip)
            notes.extend([
                "{} (static)".format(a)
                for a in configured_ip_addresses
                ])
            if dev.config.get('dhcp{v}'.format(v=v)):
                if v == 4:
                    fam = AF_INET
                elif v == 6:
                    fam = AF_INET6
                fam_addresses = []
                if dev.info is not None:
                    for a in dev.info.addresses.values():
                        if a.family == fam and a.source == 'dhcp':
                            fam_addresses.append("{} (from dhcp)".format(
                                a.address))
                if fam_addresses:
                    notes.extend(fam_addresses)
                else:
                    notes.append(
                        _("DHCPv{v} has supplied no addresses").format(v=v))
        if notes:
            notes = ", ".join(notes)
        else:
            notes = '-'
        return (dev.name, dev.type, notes)

    def new_link(self, new_dev):
        if new_dev in self.dev_to_row:
            self.update_link(new_dev)
            return
        for i, cur_dev in enumerate(self.cur_netdevs):
            if cur_dev.name > new_dev.name:
                netdev_i = i
                break
        else:
            netdev_i = len(self.cur_netdevs)
        new_rows = self._rows_for_device(new_dev, netdev_i)
        self.device_table.insert_rows(3*netdev_i+1, new_rows)

    def update_link(self, dev):
        row = self.dev_to_row[dev]
        self.device_table.invalidate()
        for i, text in enumerate(self._cells_for_device(dev)):
            row.columns[2*(i+1)].set_text(text)

    def del_link(self, dev):
        log.debug("del_link %s", (dev in self.cur_netdevs))
        if dev in self.cur_netdevs:
            netdev_i = self.cur_netdevs.index(dev)
            self.device_table.remove_rows(3*netdev_i, 3*(netdev_i+1))
            del self.cur_netdevs[netdev_i]
        if isinstance(self._w, StretchyOverlay):
            stretchy = self._w.stretchy
            if getattr(stretchy, 'device', None) is dev:
                self.remove_overlay()

    def _rows_for_device(self, dev, netdev_i=None):
        if netdev_i is None:
            netdev_i = len(self.cur_netdevs)
        rows = []
        name, typ, addresses = self._cells_for_device(dev)
        actions = []
        for action in NetDevAction:
            meth = getattr(self, '_action_' + action.name)
            opens_dialog = getattr(meth, 'opens_dialog', False)
            if dev.supports_action(action):
                actions.append(
                    (_(action.value), True, (action, meth), opens_dialog))
        menu = ActionMenu(actions)
        connect_signal(menu, 'action', self._action, dev)
        row = make_action_menu_row([
            Text("["),
            Text(name),
            Text(typ),
            Text(addresses, wrap='clip'),
            menu,
            Text("]"),
            ], menu)
        self.dev_to_row[dev] = row.base_widget
        self.cur_netdevs[netdev_i:netdev_i] = [dev]
        rows.append(row)
        if dev.type == "vlan":
            info = _("VLAN {id} on interface {link}").format(
                **dev.config)
        elif dev.type == "bond":
            info = _("bond master for {}").format(
                ', '.join(dev.config['interfaces']))
        else:
            info = " / ".join([
                dev.info.hwaddr, dev.info.vendor, dev.info.model])
        rows.append(Color.info_minor(TableRow([
            Text(""),
            (4, Text(info)),
            Text("")])))
        rows.append(Color.info_minor(TableRow([(4, Text(""))])))
        return rows

    def _build_model_inputs(self):
        rows = []
        rows.append(TableRow([
            Color.info_minor(Text(header))
            for header in ["", "NAME", "TYPE", "NOTES / ADDRESSES", ""]]))
        for dev in self.model.get_all_netdevs():
            rows.extend(self._rows_for_device(dev))
        return rows

    def _create_bond(self, sender=None):
        self.show_stretchy_overlay(BondStretchy(self))

    def show_network_error(self, action, info=None):
        self.error_showing = True
        self.bottom.contents[0:0] = [
            (Color.info_error(self.error), self.bottom.options()),
            (Text(""), self.bottom.options()),
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

    def done(self, result=None):
        if self.error_showing:
            self.bottom.contents[0:2] = []
        self.controller.network_finish(self.model.render())

    def cancel(self, button=None):
        self.controller.cancel()
