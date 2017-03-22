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
from subiquitycore.ui.buttons import menu_btn
from subiquitycore.ui.container import ListBox
from subiquitycore.ui.utils import Padding
from subiquitycore.ui.interactive import RestrictedEditor, StringEditor
from subiquitycore.ui.form import Form, FormField, StringField


log = logging.getLogger('subiquitycore.network.network_configure_ipv4_interface')

ip_families = {
    4: {
        'address_cls': ipaddress.IPv4Address,
        'network_cls': ipaddress.IPv4Network,
    },
    6: {
        'address_cls': ipaddress.IPv6Address,
        'network_cls': ipaddress.IPv6Network,
    }
}


class IPField(FormField):
    def __init__(self, *args, **kw):
        self.has_mask = kw.pop('has_mask', False)
        super().__init__(*args, **kw)
    def _make_widget(self, form):
        if form.ip_version == 6:
            return StringEditor()
        else:
            if self.has_mask:
                allowed = '[0-9./]'
            else:
                allowed = '[0-9.]'
            return RestrictedEditor(allowed)


class NetworkConfigForm(Form):

    def __init__(self, ip_version):
        self.ip_version = ip_version
        super().__init__()
        fam = ip_families[ip_version]
        self.ip_address_cls = fam['address_cls']
        self.ip_network_cls = fam['network_cls']

    subnet = IPField("Subnet:", has_mask=True)
    address = IPField("Address:")
    gateway = IPField("Gateway:")
    nameservers = StringField("Name servers:", help="IP addresses, comma separated")
    searchdomains = StringField("Search domains:", help="Domains, comma separated")

    def clean_subnet(self, subnet):
        log.debug("clean_subnet %r", subnet)
        if '/' not in subnet:
            raise ValueError("should be in CIDR form (xx.xx.xx.xx/yy)")
        return self.ip_network_cls(subnet)

    def clean_address(self, address):
        address = self.ip_address_cls(address)
        try:
            subnet = self.subnet.value
        except ValueError:
            return
        if address not in subnet:
            raise ValueError("'%s' is not contained in '%s'" % (address, subnet))
        return address

    def clean_gateway(self, gateway):
        if not gateway:
            return None
        return self.ip_address_cls(gateway)

    def clean_nameservers(self, value):
        nameservers = []
        for ns in value.split(','):
            ns = ns.strip()
            if ns:
                nameservers.append(ipaddress.ip_address(ns))
        return nameservers

    def clean_searchdomains(self, value):
        domains = []
        for domain in value.split(','):
            domain = domain.strip()
            if domain:
                domains.append(domain)
        return domains


class BaseNetworkConfigureManualView(BaseView):

    def __init__(self, model, controller, name):
        self.model = model
        self.controller = controller
        self.dev = self.model.get_netdev_by_name(name)
        self.is_gateway = False
        self.form = NetworkConfigForm(self.ip_version)
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        self.form.subnet.help = "CIDR e.g. %s"%(self.example_address,)
        configured_addresses = self.dev.configured_ip_addresses_for_version(self.ip_version)
        if configured_addresses:
            addr = ipaddress.ip_interface(configured_addresses[0])
            self.form.subnet.value = str(addr.network)
            self.form.address.value = str(addr.ip)
        configured_gateway = self.dev.configured_gateway_for_version(self.ip_version)
        if configured_gateway:
            self.form.gateway.value = configured_gateway
        self.form.nameservers.value = ', '.join(self.dev.configured_nameservers)
        self.form.searchdomains.value = ', '.join(self.dev.configured_searchdomains)
        self.error = Text("", align='center')
        #self.set_as_default_gw_button = Pile(self._build_set_as_default_gw_button())
        body = [
            Padding.center_79(self.form.as_rows(self)),
            #Padding.line_break(""),
            #Padding.center_79(self.set_as_default_gw_button),
            Padding.line_break(""),
            Padding.fixed_10(self.form.buttons)
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

    def done(self, sender):
        # XXX this converting from and to and from strings thing is a bit out of hand.
        gateway = self.form.gateway.value
        if gateway is not None:
            gateway = str(gateway)
        result = {
            'network': str(self.form.subnet.value),
            'address': str(self.form.address.value),
            'gateway': gateway,
            'nameservers': map(str, self.form.nameservers.value),
            'searchdomains': self.form.searchdomains.value,
        }
        self.dev.remove_ip_networks_for_version(self.ip_version)
        self.dev.remove_nameservers()
        self.dev.add_network(self.ip_version, result)

        # return
        self.controller.prev_view()

    def cancel(self, sender):
        self.model.default_gateway = None
        self.controller.prev_view()

class NetworkConfigureIPv4InterfaceView(BaseNetworkConfigureManualView):
    ip_version = 4
    example_address = '192.168.9.0/24'


class NetworkConfigureIPv6InterfaceView(BaseNetworkConfigureManualView):
    ip_version = 6
    example_address = 'fde4:8dba:82e1::/64'
