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

from urwid import Text, Pile, ListBox, Columns
from subiquity.view import ViewPolicy
from subiquity.ui.buttons import done_btn, menu_btn, cancel_btn
from subiquity.ui.utils import Color, Padding
from subiquity.ui.interactive import StringEditor
import logging

log = logging.getLogger('subiquity.network.network_configure_ipv4_interface')


class NetworkConfigureIPv4InterfaceView(ViewPolicy):
    def __init__(self, model, signal, iface):
        self.model = model
        self.signal = signal
        self.iface = iface
        self.gateway_input = StringEditor(caption="")  # FIXME: ipaddr_editor
        self.address_input = StringEditor(caption="")  # FIXME: ipaddr_editor
        self.subnet_input = StringEditor(caption="")  # FIXME: ipaddr_editor
        self.nameserver_input = \
            StringEditor(caption="")  # FIXME: ipaddr_editor
        self.searchpath_input = \
            StringEditor(caption="")  # FIXME: ipaddr_editor
        body = [
            Padding.center_79(self._build_iface_inputs()),
            Padding.line_break(""),
            Padding.center_79(self._build_set_as_default_gw_button()),
            Padding.center_20(self._build_buttons())
        ]
        super().__init__(ListBox(body))

    def _build_iface_inputs(self):
        col1 = [
            Columns(
                [
                    ("weight", 0.2, Text("Subnet")),
                    ("weight", 0.3,
                     Color.string_input(self.subnet_input,
                                        focus_map="string_input focus")),
                    ("weight", 0.5, Text("CIDR e.g. 192.168.9.0/24"))
                ], dividechars=2
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Address")),
                    ("weight", 0.3,
                     Color.string_input(self.address_input,
                                        focus_map="string_input focus")),
                    ("weight", 0.5, Text(""))
                ], dividechars=2
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Gateway")),
                    ("weight", 0.3,
                     Color.string_input(self.gateway_input,
                                        focus_map="string_input focus")),
                    ("weight", 0.5, Text(""))
                ], dividechars=2
            )
        ]
        return Pile(col1)

    def _build_set_as_default_gw_button(self):
        ifaces = self.model.get_interfaces()
        if len(ifaces) > 1:
            btn = menu_btn(label="Set this as default gateway",
                           on_press=self.set_default_gateway)
        else:
            btn = Text("This will be your default gateway")
        return Pile([btn])

    def set_default_gateway(self, button):
        if self.gateway_input.value:
            self.model.default_gateway = self.gateway_input.value

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def done(self, btn):
        result = {
            'subnet_type': 'static',
            'network': self.subnet_input.value,
            'address': self.address_input.value,
            'gateway': self.gateway_input.value,
            'nameserver': self.nameserver_input.value,
            'searchpath': self.searchpath_input.value,
        }
        try:
            self.model.remove_subnets(self.iface)
            self.model.add_subnet(self.iface, **result)
        except ValueError:
            log.exception('Failed to manually configure interface')
            self.model.configure_iface_from_info(self.iface)
            # FIXME: set error message in UX ala identity
            return

        # return
        self.signal.prev_signal()

    def cancel(self, button):
        self.model.default_gateway = None
        self.signal.prev_signal()
