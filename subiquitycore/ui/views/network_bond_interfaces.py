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

from urwid import Text, CheckBox
from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import cancel_btn, done_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.interactive import Selector
from subiquitycore.ui.utils import Color, Padding
import logging

log = logging.getLogger('subiquitycore.ui.bond_interfaces')


class NetworkBondInterfacesView(BaseView):
    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.bond_iface = None
        self.bond_mode = Selector(self.model.bonding_modes.values())
        self.selected_ifaces = []
        body = [
            Padding.center_50(self._build_iface_selection()),
            Padding.line_break(""),
            Padding.center_50(self._build_bondmode_configuration()),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        super().__init__(ListBox(body))

    def _build_iface_selection(self):
        log.debug('bond: _build_iface_selection')
        items = [
            Text("INTERFACE SELECTION")
        ]
        all_iface_names = self.model.get_all_interface_names()
        avail_ifnames = [iface for iface in all_iface_names
                         if not self.model.iface_is_bonded(iface)]
        log.debug('available for bonding: {}'.format(avail_ifnames))

        if len(avail_ifnames) == 0:
            log.debug('Nothing available...')
            return Pile([Color.info_minor(Text("No available interfaces."))])

        for ifname in avail_ifnames:
            device = self.model.get_interface(ifname)
            device_speed = self.model.iface_get_speed(ifname)
            iface_string = "{}     {},     {}".format(device.ifname,
                                                      device.ip4,
                                                      device_speed)
            log.debug('bond: iface_string={}'.format(iface_string))
            self.selected_ifaces.append(CheckBox(iface_string))

        items += self.selected_ifaces
        log.debug('iface_select: items: {}'.format(items))
        return Pile(items)

    def _build_bondmode_configuration(self):
        log.debug('bond: _build_bondmode_configuration')
        items = [
            Text("BOND CONFIGURATION"),
            Columns(
                [
                    ("weight", 0.2, Text("Bonding Mode", align="right")),
                    ("weight", 0.3, Color.string_input(self.bond_mode))
                ],
                dividechars=4
            ),
        ]
        log.debug('bond_mode: items: {}'.format(items))
        return Pile(items)

    def _build_buttons(self):
        log.debug('bond: _build_buttons')
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        items = [
            Color.button(done),
            Color.button(cancel)
        ]
        log.debug('buttons: items: {}'.format(items))
        return Pile(items)

    def done(self, result):
        selected_labels = [x.get_label() for x in self.selected_ifaces
                           if x.state]
        if len(selected_labels) < 2:
            log.debug('Not enough interfaces for bonding')
            # FIXME: raise error message?
            return

        # unpack label into iface name
        bond_interfaces = []
        for label in selected_labels:
            bond_interfaces.append(label.split(' ')[0])

        result = {
            'bond-interfaces': bond_interfaces,
            'bond-mode': self.bond_mode.value,
        }
        log.debug('bonding_done: result = {}'.format(result))

        # generate bond name based on number of bonds created
        existing_bonds = self.model.get_bond_masters()
        bond_name = "bond{}".format(int(len(existing_bonds)))

        try:
            self.model.add_bond(ifname=bond_name,
                                interfaces=result['bond-interfaces'],
                                params={'bond-mode': result['bond-mode']},
                                subnets=[])
        except ValueError:
            log.exception('Failed to add bond: {}'.format(result))
            return

        log.debug('bond: successful bond creation')
        self.controller.prev_view()

    def cancel(self, button):
        log.debug('bond: button_cancel')
        self.controller.prev_view()
