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
from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import done_btn, menu_btn, cancel_btn
from subiquitycore.ui.utils import Color, Padding
from subiquitycore.ui.interactive import StringEditor
import logging

log = logging.getLogger('subiquitycore.network.network_configure_ipv4_interface')


class NetworkConfigureIPv4InterfaceView(BaseView):
    def __init__(self, model, signal, iface):
        self.model = model
        self.signal = signal
        self.ifname = iface
        self.iface = self.model.get_interface(self.ifname)
        self.gateway_input = StringEditor(caption="")  # FIXME: ipaddr_editor
        self.address_input = StringEditor(caption="")  # FIXME: ipaddr_editor
        self.subnet_input = StringEditor(caption="")  # FIXME: ipaddr_editor
        self.error = Text("", align='center')
        self.nameserver_input = \
            StringEditor(caption="")  # FIXME: ipaddr_editor
        self.searchdomains_input = \
            StringEditor(caption="")  # FIXME: ipaddr_editor
        body = [
            Padding.center_79(self._build_iface_inputs()),
            Padding.line_break(""),
            Padding.center_79(self._build_set_as_default_gw_button()),
            Padding.line_break(""),
            Padding.center_90(Color.info_error(self.error)),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
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
        ifaces = self.model.get_all_interface_names()
        if len(ifaces) > 1:
            btn = menu_btn(label="Set this as default gateway",
                           on_press=self.set_default_gateway)
        else:
            btn = Text("This will be your default gateway")
        return Pile([btn])

    def set_default_gateway(self, button):
        if self.gateway_input.value:
            try:
                self.model.set_default_gateway(self.gateway_input.value)
            except ValueError:
                # FIXME: set error message UX ala identity
                pass

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def validate(self):
        try:
            if '/' not in self.subnet_input.value:
                raise ValueError("Network should be in CIDR form (xx.xx.xx.xx/yy)")

            netmask = self.subnet_input.value.split('/')[1]
            if int(netmask) > 32 or int(netmask) < 0:
                raise ValueError("CIDR netmask value should be between 0 and 32")
        except:
            raise

    def done(self, btn):
        result = {
            'network': self.subnet_input.value,
            'address': self.address_input.value,
            'gateway': self.gateway_input.value,
            'nameserver': self.nameserver_input.value,
            'searchdomains': self.searchdomains_input.value,
        }
        try:
            self.validate()
            self.iface.remove_networks()
            self.iface.add_network(result)
        except ValueError as e:
            error = 'Failed to manually configure interface: {}'.format(e)
            log.exception(error)
            self.error.set_text(str(e))
            #self.iface.configure_from_info()
            # FIXME: set error message in UX ala identity
            return

        # return
        self.signal.prev_signal()

    def cancel(self, button):
        self.model.default_gateway = None
        self.signal.prev_signal()
