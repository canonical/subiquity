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

from urwid import (
    connect_signal,
    Text,
    )

from subiquitycore.models.network import (
    addr_version,
    NetDevAction,
    )
from subiquitycore.ui.actionmenu import ActionMenu
from subiquitycore.ui.buttons import (
    back_btn,
    done_btn,
    menu_btn,
    )
from subiquitycore.ui.container import (
    Pile,
    )
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.stretchy import StretchyOverlay
from subiquitycore.ui.table import ColSpec, TablePile, TableRow
from subiquitycore.ui.utils import (
    button_pile,
    Color,
    make_action_menu_row,
    screen,
    )
from subiquitycore.ui.width import widget_width
from .network_configure_manual_interface import (
    AddVlanStretchy,
    BondStretchy,
    EditNetworkStretchy,
    ViewInterfaceInfo,
    )
from .network_configure_wlan_interface import NetworkConfigureWLANStretchy

from subiquitycore.view import BaseView


log = logging.getLogger('subiquitycore.views.network')


def _stretchy_shower(cls, *args):
    def impl(self, name, device):
        stretchy = cls(self, device, *args)
        stretchy.attach_context(self.controller.context.child(name))
        self.show_stretchy_overlay(stretchy)
    impl.opens_dialog = True
    return impl


class NetworkView(BaseView):
    title = _("Network connections")
    excerpt = _("Configure at least one interface this server can use to talk "
                "to other machines, and which preferably provides sufficient "
                "access for updates.")

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.dev_to_table = {}
        self.cur_netdevs = []
        self.error = Text("", align='center')

        self.device_colspecs = {
            0: ColSpec(rpad=1),
            3: ColSpec(min_width=15),
            4: ColSpec(can_shrink=True, rpad=1),
            }

        self.device_pile = Pile(self._build_model_inputs())

        self._create_bond_btn = menu_btn(
            _("Create bond"), on_press=self._create_bond)
        bp = button_pile([self._create_bond_btn])
        bp.align = 'left'

        rows = [
            self.device_pile,
            bp,
        ]

        self.buttons = button_pile([
                    done_btn("TBD", on_press=self.done),  # See _route_watcher
                    back_btn(_("Back"), on_press=self.cancel),
                    ])
        self.bottom = Pile([
            ('pack', self.buttons),
        ])

        self.controller.network_event_receiver.add_default_route_watcher(
            self._route_watcher)

        self.error_showing = False

        super().__init__(screen(
            rows=rows,
            buttons=self.bottom,
            focus_buttons=True,
            excerpt=_(self.excerpt)))

    _action_INFO = _stretchy_shower(ViewInterfaceInfo)
    _action_EDIT_WLAN = _stretchy_shower(NetworkConfigureWLANStretchy)
    _action_EDIT_IPV4 = _stretchy_shower(EditNetworkStretchy, 4)
    _action_EDIT_IPV6 = _stretchy_shower(EditNetworkStretchy, 6)
    _action_EDIT_BOND = _stretchy_shower(BondStretchy)
    _action_ADD_VLAN = _stretchy_shower(AddVlanStretchy)

    def _action_DELETE(self, name, device):
        with self.controller.context.child(name):
            touched_devs = set()
            if device.type == "bond":
                for name in device.config['interfaces']:
                    touched_devs.add(self.model.get_netdev_by_name(name))
            device.config = None
            self.del_link(device)
            for dev in touched_devs:
                self.update_link(dev)
            self.controller.apply_config()

    def _action(self, sender, action, device):
        action, meth = action
        meth("{}/{}".format(device.name, action.name), device)

    def _route_watcher(self, routes):
        log.debug('view route_watcher %s', routes)
        if routes:
            label = _("Done")
        else:
            label = _("Continue without network")
        self.buttons.base_widget[0].set_label(label)
        self.buttons.width = max(
            14,
            widget_width(self.buttons.base_widget[0]),
            widget_width(self.buttons.base_widget[1]),
            )

    def show_apply_spinner(self):
        s = Spinner(self.controller.app.aio_loop)
        s.start()
        c = TablePile([
            TableRow([
                Text(_("Applying changes")),
                s,
                ]),
            ], align='center')
        self.bottom.contents[0:0] = [
            (c, self.bottom.options()),
            (Text(""), self.bottom.options()),
            ]

    def hide_apply_spinner(self):
        if len(self.bottom.contents) > 2:
            self.bottom.contents[0:2] = []

    def _notes_for_device(self, dev):
        notes = []
        if dev.type == "eth" and not dev.info.is_connected:
            notes.append(_("not connected"))
        for dev2 in self.model.get_all_netdevs():
            if dev2.type != "bond":
                continue
            if dev.name in dev2.config.get('interfaces', []):
                notes.append(
                    _("enslaved to {device}").format(device=dev2.name))
                break
        if notes:
            notes = ", ".join(notes)
        else:
            notes = '-'
        return notes

    def _address_rows_for_device(self, dev):
        address_info = []
        dhcp_addresses = dev.dhcp_addresses()
        for v in 4, 6:
            if dev.dhcp_enabled(v):
                label = Text("DHCPv{v}".format(v=v))
                addrs = dhcp_addresses.get(v)
                if addrs:
                    address_info.extend(
                        [(label, Text(addr)) for addr in addrs])
                elif dev.dhcp_state(v) == "PENDING":
                    s = Spinner(self.controller.app.aio_loop, align='left')
                    s.rate = 0.3
                    s.start()
                    address_info.append((label, s))
                elif dev.dhcp_state(v) == "TIMEDOUT":
                    address_info.append((label, Text(_("timed out"))))
                elif dev.dhcp_state(v) == "RECONFIGURE":
                    address_info.append((label, Text("-")))
                else:
                    address_info.append((
                        label,
                        Text(
                            _("unknown state {state}".format(
                                state=dev.dhcp_state(v))))
                        ))
            else:
                addrs = []
                for ip in dev.config.get('addresses', []):
                    if addr_version(ip) == v:
                        addrs.append(str(ip))
                if addrs:
                    address_info.append(
                        # Network addressing mode (static/dhcp/disabled)
                        (Text(_('static')), Text(', '.join(addrs))))
        if len(address_info) == 0:
            # Do not show an interface as disabled if it is part of a bond or
            # has a vlan on it.
            if not dev.is_used:
                reason = dev.disabled_reason
                if reason is None:
                    reason = ""
                # Network addressing mode (static/dhcp/disabled)
                address_info.append((Text(_("disabled")), Text(reason)))
        rows = []
        for label, value in address_info:
            rows.append(TableRow([Text(""), label, (2, value)]))
        return rows

    def new_link(self, new_dev):
        log.debug(
            "new_link %s %s %s",
            new_dev.name, new_dev.ifindex, (new_dev in self.cur_netdevs))
        if new_dev in self.dev_to_table:
            self.update_link(new_dev)
            return
        for i, cur_dev in enumerate(self.cur_netdevs):
            if cur_dev.name > new_dev.name:
                netdev_i = i
                break
        else:
            netdev_i = len(self.cur_netdevs)
        w = self._device_widget(new_dev, netdev_i)
        self.device_pile.contents[netdev_i+1:netdev_i+1] = [
            (w, self.device_pile.options('pack'))]

    def update_link(self, dev):
        log.debug(
            "update_link %s %s %s",
            dev.name, dev.ifindex, (dev in self.cur_netdevs))
        if dev not in self.cur_netdevs:
            return
        # Update the display of dev to represent the current state.
        #
        # The easiest way of doing this would be to just create a new table
        # widget for the device and replace the current one with it. But that
        # is jarring if the menu for the current device is open, so instead we
        # overwrite the content of the first (menu) row of the old table with
        # the contents of the first row of the new table, and replace all other
        # rows of the old table with new content (which is OK as they cannot be
        # focused).
        old_table = self.dev_to_table[dev]
        first_row = old_table.table_rows[0].base_widget
        first_row.cells[1][1].set_text(dev.name)
        first_row.cells[2][1].set_text(dev.type)
        first_row.cells[3][1].set_text(self._notes_for_device(dev))
        old_table.remove_rows(1, len(old_table.table_rows))
        old_table.insert_rows(1, self._address_rows_for_device(dev))

    def _remove_row(self, netdev_i):
        # MonitoredFocusList clamps the focus position to the new
        # length of the list when you remove elements but it doesn't
        # check that that the element it moves the focus to is
        # selectable...
        new_length = len(self.device_pile.contents) - 1
        refocus = self.device_pile.focus_position >= new_length
        del self.device_pile.contents[netdev_i]
        if refocus:
            self.device_pile._select_last_selectable()
        else:
            while not self.device_pile.focus.selectable():
                self.device_pile.focus_position += 1
            self.device_pile.focus._select_first_selectable()

    def del_link(self, dev):
        log.debug(
            "del_link %s %s %s",
            dev.name, dev.ifindex, (dev in self.cur_netdevs))
        # If a virtual device disappears while we still have config
        # for it, we assume it will be back soon.
        if dev.is_virtual and dev.config is not None:
            return
        if dev in self.cur_netdevs:
            netdev_i = self.cur_netdevs.index(dev)
            self._remove_row(netdev_i+1)
            del self.cur_netdevs[netdev_i]
            del self.dev_to_table[dev]
        if isinstance(self._w, StretchyOverlay):
            stretchy = self._w.stretchy
            if getattr(stretchy, 'device', None) is dev:
                self.remove_overlay()

    def _device_widget(self, dev, netdev_i=None):
        # Create the widget for a nic. This consists of a Pile containing a
        # table, an info line and a blank line. The first row of the table is
        # the one that can be focused and has a menu for manipulating the nic,
        # the other rows summarize its address config.
        #   [ name type notes   ▸ ]   \
        #     address info            | <- table
        #     more address info       /
        #   mac / vendor info / model info
        #   <blank line>
        if netdev_i is None:
            netdev_i = len(self.cur_netdevs)
        self.cur_netdevs[netdev_i:netdev_i] = [dev]

        actions = []
        for action in NetDevAction:
            meth = getattr(self, '_action_' + action.name)
            opens_dialog = getattr(meth, 'opens_dialog', False)
            if dev.supports_action(action):
                actions.append(
                    (action.str(), True, (action, meth), opens_dialog))

        menu = ActionMenu(actions)
        connect_signal(menu, 'action', self._action, dev)

        trows = [make_action_menu_row([
            Text("["),
            Text(dev.name),
            Text(dev.type),
            Text(self._notes_for_device(dev), wrap='clip'),
            menu,
            Text("]"),
            ], menu)] + self._address_rows_for_device(dev)

        table = TablePile(trows, colspecs=self.device_colspecs, spacing=2)
        self.dev_to_table[dev] = table
        table.bind(self.heading_table)

        if dev.type == "vlan":
            info = _("VLAN {id} on interface {link}").format(
                **dev.config)
        elif dev.type == "bond":
            info = _("bond master for {interfaces}").format(
                interfaces=', '.join(dev.config['interfaces']))
        else:
            info = " / ".join([
                dev.info.hwaddr, dev.info.vendor, dev.info.model])

        return Pile([
            ('pack', table),
            ('pack', Color.info_minor(Text("  " + info))),
            ('pack', Text("")),
            ])

    def _build_model_inputs(self):
        self.heading_table = TablePile([
            TableRow([
                Color.info_minor(Text(header)) for header in [
                    "", "NAME", "TYPE", "NOTES", "",
                    ]
                ])
            ],
            spacing=2, colspecs=self.device_colspecs)
        rows = [self.heading_table]
        for dev in self.model.get_all_netdevs():
            rows.append(self._device_widget(dev))
        return rows

    def _create_bond(self, sender=None):
        stretchy = BondStretchy(self)
        stretchy.attach_context(self.controller.context.child("add_bond"))
        self.show_stretchy_overlay(stretchy)

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
        self.controller.network_event_receiver.remove_default_route_watcher(
            self._route_watcher)
        self.controller.done()

    def cancel(self, button=None):
        self.controller.network_event_receiver.remove_default_route_watcher(
            self._route_watcher)
        self.controller.cancel()
