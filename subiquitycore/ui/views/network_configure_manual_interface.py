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

import logging
import ipaddress

from urwid import connect_signal, Text

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import done_btn, menu_btn, cancel_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.utils import Color, Padding
from subiquitycore.ui.validation import Toggleable, ValidatingWidgetSet


log = logging.getLogger('subiquitycore.network.network_configure_ipv4_interface')


class BaseNetworkConfigureManualView(BaseView):

    def __init__(self, model, controller, name):
        self.model = model
        self.controller = controller
        self.dev = self.model.get_netdev_by_name(name)
        self.is_gateway = False
        self.subnet_input = StringEditor(caption="")  # FIXME: ipaddr_editor
        self.address_input = StringEditor(caption="")  # FIXME: ipaddr_editor
        configured_addresses = self.dev.configured_ip_addresses_for_version(self.ip_version)
        if configured_addresses:
            addr = ipaddress.ip_interface(configured_addresses[0])
            self.subnet_input.value = str(addr.network)
            self.address_input.value = str(addr.ip)
        self.gateway_input = StringEditor(caption="")  # FIXME: ipaddr_editor
        configured_gateway = self.dev.configured_gateway_for_version(self.ip_version)
        if configured_gateway:
            self.gateway_input.value = configured_gateway
        self.nameserver_input = StringEditor(caption="")  # FIXME: ipaddr_list_editor
        self.nameserver_input.value = ', '.join(self.dev.configured_nameservers)
        self.searchdomains_input = StringEditor(caption="")  # FIXME: ipaddr_list_editor
        self.searchdomains_input.value = ', '.join(self.dev.configured_searchdomains)
        self.error = Text("", align='center')
        #self.set_as_default_gw_button = Pile(self._build_set_as_default_gw_button())
        self.buttons = self._build_buttons()
        body = [
            Padding.center_79(self._build_iface_inputs()),
            #Padding.line_break(""),
            #Padding.center_79(self.set_as_default_gw_button),
            Padding.line_break(""),
            Padding.center_90(Color.info_error(self.error)),
            Padding.line_break(""),
            Padding.fixed_10(self.buttons)
        ]
        super().__init__(ListBox(body))

    def refresh_model_inputs(self):
        try:
            self.dev = self.model.get_netdev_by_name(self.dev.name)
        except KeyError:
            # The interface is gone
            self.controller.prev_view()
            self.controller.prev_view()
            return

    def _vws(self, caption, input, help, validator=None):
        text = Text(caption, align="right")
        decorated = Toggleable(input, 'string_input')
        captioned = Columns(
                [
                    ("weight", 0.2, text),
                    ("weight", 0.3,
                     Color.string_input(input,
                                        focus_map="string_input focus")),
                    ("weight", 0.5, Text(help))
                ], dividechars=2
            )
        return ValidatingWidgetSet(captioned, decorated, input, validator)

    def _build_iface_inputs(self):
        self.all_vws = [
            self._vws("Subnet:", self.subnet_input, "CIDR e.g. %s"%(self.example_address,), self._validate_subnet),
            self._vws("Address:", self.address_input, ""),
            self._vws("Gateway:", self.gateway_input, ""),
            self._vws("Name servers:", self.nameserver_input, "IP addresses, comma separated"),
            self._vws("Search domains:", self.searchdomains_input, "Domains, comma separated"),
        ]
        for vw in self.all_vws:
            connect_signal(vw, 'validated', self._validated)
        return Pile(self.all_vws)

    def _validate_subnet(self):
        subnet = self.subnet_input.value
        if '/' not in subnet:
            return "should be in CIDR form (xx.xx.xx.xx/yy)"

    def _validated(self, sender):
        error = False
        for w in self.all_vws:
            if w.has_error():
                error = True
                break
        if error:
            self.buttons[0].disable()
            self.buttons.focus_position = 1
        else:
            self.buttons[0].enable()

    def _build_set_as_default_gw_button(self):
        devs = self.model.get_all_netdevs()

        self.is_gateway = self.model.v4_gateway_dev == self.dev.name

        if not self.is_gateway and len(devs) > 1:
            btn = menu_btn(label="Set this as default gateway",
                           on_press=self.set_default_gateway)
        else:
            btn = Text("This will be your default gateway")

        return [btn]

    def set_default_gateway(self, button):
        if self.gateway_input.value:
            try:
                self.model.set_default_v4_gateway(self.dev.name,
                                                  self.gateway_input.value)
                self.is_gateway = True
                self.set_as_default_gw_button.contents = \
                    [ (obj, ('pack', None)) \
                           for obj in self._build_set_as_default_gw_button() ]
            except ValueError:
                # FIXME: set error message UX ala identity
                pass

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Toggleable(done, 'button'),
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def validate(self, result):
        if '/' not in result['network']:
            raise ValueError("Subnet: should be in CIDR form (xx.xx.xx.xx/yy)")

        try:
            network = self.ip_network_cls(result['network'])
        except ValueError as v:
            raise ValueError("Subnet: " + str(v))
        try:
            address = self.ip_address_cls(result['address'])
        except ValueError as v:
            raise ValueError("Address: " + str(v))
        if address not in network:
            raise ValueError("Address: '%s' is not contained in '%s'" % (address, network))
        try:
            self.ip_address_cls(result['gateway'])
        except ValueError as v:
            raise ValueError("Gateway: " + str(v))
        for ns in result['nameservers']:
            try:
                ipaddress.ip_address(ns)
            except ValueError as v:
                raise ValueError("Nameserver " + str(v))

    def done(self, btn):
        searchdomains = []
        for sd in self.searchdomains_input.value.split(','):
            sd = sd.strip()
            if sd:
                searchdomains.append(sd.strip())
        nameservers = []
        for ns in self.nameserver_input.value.split(','):
            ns = ns.strip()
            if ns:
                nameservers.append(ns.strip())
        result = {
            'network': self.subnet_input.value,
            'address': self.address_input.value,
            'gateway': self.gateway_input.value,
            'nameservers': nameservers,
            'searchdomains': searchdomains,
        }
        try:
            self.validate(result)
        except ValueError as e:
            error = 'Failed to manually configure interface: {}'.format(e)
            log.exception(error)
            self.error.set_text(str(e))
            return
        self.dev.remove_ip_networks_for_version(self.ip_version)
        self.dev.remove_nameservers()
        self.dev.add_network(self.ip_version, result)

        # return
        self.controller.prev_view()

    def cancel(self, button):
        self.model.default_gateway = None
        self.controller.prev_view()

class NetworkConfigureIPv4InterfaceView(BaseNetworkConfigureManualView):
    ip_version = 4
    ip_address_cls = ipaddress.IPv4Address
    ip_network_cls = ipaddress.IPv4Network
    example_address = '192.168.9.0/24'


class NetworkConfigureIPv6InterfaceView(BaseNetworkConfigureManualView):
    ip_version = 6
    ip_address_cls = ipaddress.IPv6Address
    ip_network_cls = ipaddress.IPv6Network
    example_address = 'fde4:8dba:82e1::/64'
