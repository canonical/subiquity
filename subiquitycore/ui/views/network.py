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
    DHCPState,
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
    WidgetWrap,
    )
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.stretchy import StretchyOverlay
from subiquitycore.ui.table import ColSpec, TablePile, TableRow
from subiquitycore.ui.utils import (
    button_pile,
    Color,
    make_action_menu_row,
    rewrap,
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


log = logging.getLogger('subiquitycore.ui.views.network')


def _stretchy_shower(cls, *args):
    def impl(self, name, device):
        stretchy = cls(self, device, *args)
        stretchy.attach_context(self.controller.context.child(name))
        self.show_stretchy_overlay(stretchy)
    impl.opens_dialog = True
    return impl


class NetworkDeviceTable(WidgetWrap):
    def __init__(self, parent, dev_info):
        self.parent = parent
        self.dev_info = dev_info
        super().__init__(self._create())

    def _create(self):
        # Create the widget for a nic. This consists of a Pile containing a
        # table, an info line and a blank line. The first row of the table is
        # the one that can be focused and has a menu for manipulating the nic,
        # the other rows summarize its address config.
        #   [ name type notes   ▸ ]   \
        #     address info            | <- table
        #     more address info       /
        #   mac / vendor info / model info
        #   <blank line>

        actions = []
        for action in NetDevAction:
            meth = getattr(self.parent, '_action_' + action.name)
            opens_dialog = getattr(meth, 'opens_dialog', False)
            if action in self.dev_info.enabled_actions:
                actions.append(
                    (action.str(), True, (action, meth), opens_dialog))

        menu = ActionMenu(actions)
        connect_signal(menu, 'action', self.parent._action, self)

        trows = [make_action_menu_row([
            Text("["),
            Text(self.dev_info.name),
            Text(self.dev_info.type),
            Text(self._notes(), wrap='clip'),
            menu,
            Text("]"),
            ], menu)] + self._address_rows()

        self.table = TablePile(
            trows, colspecs=self.parent.device_colspecs, spacing=2)
        self.table.bind(self.parent.heading_table)

        if self.dev_info.type == "vlan":
            info = _("VLAN {id} on interface {link}").format(
                id=self.dev_info.vlan.id, link=self.dev_info.vlan.link)
        elif self.dev_info.type == "bond":
            info = _("bond master for {interfaces}").format(
                interfaces=', '.join(self.dev_info.bond.interfaces))
        else:
            info = " / ".join([
                self.dev_info.hwaddr,
                self.dev_info.vendor,
                self.dev_info.model,
                ])

        return Pile([
            ('pack', self.table),
            ('pack', Color.info_minor(Text("  " + info))),
            ('pack', Text("")),
            ])

    def _notes(self):
        notes = []
        if self.dev_info.type == "wlan":
            config = self.dev_info.wlan.config
            if config.ssid is not None:
                notes.append(_("ssid: {ssid}".format(ssid=config.ssid)))
            else:
                notes.append(_("not connected"))
        if not self.dev_info.is_connected:
            notes.append(_("not connected"))
        if self.dev_info.bond_master:
            notes.append(
                _("enslaved to {device}").format(
                    device=self.dev_info.bond_master))
        if notes:
            notes = ", ".join(notes)
        else:
            notes = '-'
        return notes

    def _address_rows(self):
        address_info = []
        for v, dhcp_status, static_config in (
                (4, self.dev_info.dhcp4, self.dev_info.static4),
                (6, self.dev_info.dhcp6, self.dev_info.static6),
                ):
            if dhcp_status.enabled:
                label = Text("DHCPv{v}".format(v=v))
                addrs = dhcp_status.addresses
                if addrs:
                    address_info.extend(
                        [(label, Text(addr)) for addr in addrs])
                elif dhcp_status.state == DHCPState.PENDING:
                    s = Spinner(
                        self.parent.controller.app.aio_loop, align='left')
                    s.rate = 0.3
                    s.start()
                    address_info.append((label, s))
                elif dhcp_status.state == DHCPState.TIMED_OUT:
                    address_info.append((label, Text(_("timed out"))))
                elif dhcp_status.state == DHCPState.RECONFIGURE:
                    address_info.append((label, Text("-")))
            elif static_config.addresses:
                address_info.append((
                    Text(_('static')),
                    Text(', '.join(static_config.addresses)),
                    ))
        if len(address_info) == 0 and not self.dev_info.is_used:
            reason = self.dev_info.disabled_reason
            if reason is None:
                reason = ""
            address_info.append((Text(_("disabled")), Text(reason)))
        rows = []
        for label, value in address_info:
            rows.append(TableRow([Text(""), label, (2, value)]))
        return rows

    def update(self, dev_info):
        # Update the display of dev to represent the current state.
        #
        # The easiest way of doing this would be to just create a new table
        # widget for the device and replace the current one with it. But that
        # is jarring if the menu for the current device is open, so instead we
        # overwrite the contents of the first (menu) row of the table, and
        # replace all other rows of the with new content (which is OK as they
        # cannot be focused).
        self.dev_info = dev_info
        first_row = self.table.table_rows[0].base_widget
        first_row.cells[1][1].set_text(dev_info.name)
        first_row.cells[2][1].set_text(dev_info.type)
        first_row.cells[3][1].set_text(self._notes())
        self.table.remove_rows(1, len(self.table.table_rows))
        self.table.insert_rows(1, self._address_rows())


wlan_support_install_state_texts = {
    "NOT_AVAILABLE": _("""\
A wifi device was detected but the necessary support packages were not
available.
"""),
    "INSTALLING": _("""\
Wifi support packages are being installed.
"""),
    "FAILED": _("""\
Wifi support packages failed to install. Please check the logs.
"""),
    "DONE": _("""\
Wifi support packages will be installed in the target system.
"""),
    }


class NetworkView(BaseView):
    title = _("Network connections")
    excerpt = _("Configure at least one interface this server can use to talk "
                "to other machines, and which preferably provides sufficient "
                "access for updates.")

    def __init__(self, controller, netdev_infos,
                 wlan_support_install_state="NOT_NEEDED"):
        self.controller = controller
        self.dev_name_to_table = {}
        self.cur_netdev_names = []
        self.error = Text("", align='center')

        self.device_colspecs = {
            0: ColSpec(rpad=1),
            3: ColSpec(min_width=15),
            4: ColSpec(can_shrink=True, rpad=1),
            }

        self.heading_table = TablePile([
            TableRow([
                Color.info_minor(Text(header)) for header in [
                    "", "NAME", "TYPE", "NOTES", "",
                    ]
                ])
            ],
            spacing=2, colspecs=self.device_colspecs)

        self.device_pile = Pile([self.heading_table])

        for dev_info in netdev_infos:
            self.new_link(dev_info)

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

        self.wlan_support_install_state_showing = False
        self.error_showing = False

        self.update_for_wlan_support_install_state(wlan_support_install_state)

        super().__init__(screen(
            rows=rows,
            buttons=self.bottom,
            focus_buttons=True,
            excerpt=_(self.excerpt)))

    async def _show_INFO(self, name):
        info = await self.controller.app.wait_with_text_dialog(
            self.controller.get_info_for_netdev(name), "Loading info",
            can_cancel=True)
        stretchy = ViewInterfaceInfo(self, name, info)
        stretchy.attach_context(self.controller.context.child("INFO"))
        self.show_stretchy_overlay(stretchy)

    def _action_INFO(self, name, dev_info):
        self.controller.app.aio_loop.create_task(
            self._show_INFO(dev_info.name))
    _action_INFO.opens_dialog = True

    _action_EDIT_WLAN = _stretchy_shower(NetworkConfigureWLANStretchy)
    _action_EDIT_IPV4 = _stretchy_shower(EditNetworkStretchy, 4)
    _action_EDIT_IPV6 = _stretchy_shower(EditNetworkStretchy, 6)
    _action_ADD_VLAN = _stretchy_shower(AddVlanStretchy)

    def _action_EDIT_BOND(self, name, dev_info):
        stretchy = BondStretchy(
            self, dev_info, self.get_candidate_bond_member_names())
        stretchy.attach_context(self.controller.context.child(name))
        self.show_stretchy_overlay(stretchy)

    _action_EDIT_BOND.opens_dialog = True

    def _action_DELETE(self, name, dev_info):
        with self.controller.context.child(name):
            self.controller.delete_link(dev_info.name)
            self.del_link(dev_info)

    def _action(self, sender, action, netdev_table):
        action, meth = action
        dev_info = netdev_table.dev_info
        meth("{}/{}".format(dev_info.name, action.name), dev_info)

    def update_default_routes(self, routes):
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

    def new_link(self, new_dev_info):
        log.debug(
            "new_link %s %s",
            new_dev_info.name, (new_dev_info.name in self.cur_netdev_names))
        if new_dev_info.name in self.dev_name_to_table:
            self.update_link(new_dev_info)
            return
        self.cur_netdev_names.append(new_dev_info.name)
        self.cur_netdev_names.sort()
        netdev_i = self.cur_netdev_names.index(new_dev_info.name)
        device_table = NetworkDeviceTable(self, new_dev_info)
        self.dev_name_to_table[new_dev_info.name] = device_table
        self.device_pile.contents[netdev_i+1:netdev_i+1] = [
            (device_table, self.device_pile.options('pack'))]

    def update_link(self, dev_info):
        if isinstance(self._w, StretchyOverlay):
            if hasattr(self._w.stretchy, 'update_link'):
                self._w.stretchy.update_link(dev_info)
        log.debug(
            "update_link %s %s",
            dev_info.name, (dev_info.name in self.cur_netdev_names))
        if dev_info.name not in self.cur_netdev_names:
            return
        self.dev_name_to_table[dev_info.name].update(dev_info)

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

    def del_link(self, dev_info):
        log.debug(
            "del_link %s %s",
            dev_info.name, (dev_info.name in self.cur_netdev_names))
        # If a virtual device disappears while we still have config
        # for it, we assume it will be back soon.
        if dev_info.is_virtual and dev_info.has_config:
            return
        if dev_info.name in self.cur_netdev_names:
            netdev_i = self.cur_netdev_names.index(dev_info.name)
            self._remove_row(netdev_i+1)
            del self.cur_netdev_names[netdev_i]
            del self.dev_name_to_table[dev_info.name]
        if isinstance(self._w, StretchyOverlay):
            stretchy = self._w.stretchy
            if getattr(stretchy, 'device', None) is dev_info:
                self.remove_overlay()

    def get_candidate_bond_member_names(self):
        names = []
        for table in self.dev_name_to_table.values():
            dev_info = table.dev_info
            if dev_info.type in ("vlan", "bond"):
                continue
            if dev_info.bond_master is not None:
                continue
            names.append(dev_info.name)
        return names

    def _create_bond(self, sender=None):
        stretchy = BondStretchy(
            self, None, self.get_candidate_bond_member_names())
        stretchy.attach_context(self.controller.context.child("add_bond"))
        self.show_stretchy_overlay(stretchy)

    def update_for_wlan_support_install_state(self, state):
        if state == "NOT_NEEDED":
            return
        if self.error_showing:
            start_i = 2
        else:
            start_i = 0
        if self.wlan_support_install_state_showing:
            end_i = start_i + 2
        else:
            end_i = start_i
        self.wlan_support_install_state_showing = True
        text = wlan_support_install_state_texts[state]
        self.bottom.contents[start_i:end_i] = [
            (Text(rewrap(text), align='center'), self.bottom.options()),
            (Text(""), self.bottom.options()),
            ]

    def show_network_error(self, action, info=None):
        if not self.error_showing:
            start_i = end_i = 0
            self.error_showing = True
        else:
            start_i = 0
            end_i = 2
        self.bottom.contents[start_i:end_i] = [
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
        self.controller.done()

    def cancel(self, button=None):
        self.controller.cancel()
