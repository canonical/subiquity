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
import yaml

from urwid import (
    connect_signal,
    Text,
    WidgetPlaceholder,
    )

from subiquitycore.ui.container import Pile
from subiquitycore.ui.form import (
    ChoiceField,
    Form,
    FormField,
    StringField,
    )
from subiquitycore.ui.interactive import RestrictedEditor, StringEditor
from subiquitycore.ui.stretchy import Stretchy

from subiquitycore.ui.utils import button_pile
from subiquitycore.ui.buttons import done_btn

log = logging.getLogger(
    'subiquitycore.network.network_configure_ipv4_interface')

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

    def __init__(self, ip_version, initial={}):
        self.ip_version = ip_version
        fam = ip_families[ip_version]
        self.ip_address_cls = fam['address_cls']
        self.ip_network_cls = fam['network_cls']
        super().__init__(initial)

    ok_label = _("Save")

    subnet = IPField(_("Subnet:"), has_mask=True)
    address = IPField(_("Address:"))
    gateway = IPField(_("Gateway:"))
    nameservers = StringField(_("Name servers:"),
                              help=_("IP addresses, comma separated"))
    searchdomains = StringField(_("Search domains:"),
                                help=_("Domains, comma separated"))

    def clean_subnet(self, subnet):
        log.debug("clean_subnet %r", subnet)
        if '/' not in subnet:
            raise ValueError(_("should be in CIDR form (xx.xx.xx.xx/yy)"))
        return self.ip_network_cls(subnet)

    def clean_address(self, address):
        address = self.ip_address_cls(address)
        try:
            subnet = self.subnet.value
        except ValueError:
            return
        if address not in subnet:
            raise ValueError(
                _("'%s' is not contained in '%s'") % (address, subnet))
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


network_choices = [
    (_("Automatic (DHCP)"), True, "dhcp"),
    (_("Manual"), True, "manual"),
    (_("Disabled"), True, "disable"),
    ]


class NetworkMethodForm(Form):
    ok_label = _("Save")
    method = ChoiceField("IPv{ip_version} Method: ", choices=network_choices)


class EditNetworkStretchy(Stretchy):

    def __init__(self, parent, device, ip_version):
        self.parent = parent
        self.device = device
        self.ip_version = ip_version

        self.method_form = NetworkMethodForm()
        self.method_form.method.caption = _(
            "IPv{ip_version} Method: ").format(ip_version=ip_version)
        manual_initial = {}
        if len(device.configured_ip_addresses_for_version(ip_version)) > 0:
            method = 'manual'
            addr = ipaddress.ip_interface(
                device.configured_ip_addresses_for_version(ip_version)[0])
            manual_initial = {
                'subnet': str(addr.network),
                'address': str(addr.ip),
                'nameservers': ', '.join(device.configured_nameservers),
                'searchdomains': ', '.join(device.configured_searchdomains),
            }
            gw = device.configured_gateway_for_version(ip_version)
            if gw:
                manual_initial['gateway'] = str(gw)
        elif self.device.dhcp_for_version(ip_version):
            method = 'dhcp'
        else:
            method = 'disable'

        self.method_form.method.value = method

        connect_signal(
            self.method_form.method.widget, 'select', self._select_method)

        log.debug("manual_initial %s", manual_initial)
        self.manual_form = NetworkConfigForm(ip_version, manual_initial)

        connect_signal(self.method_form, 'submit', self.done)
        connect_signal(self.manual_form, 'submit', self.done)
        connect_signal(self.method_form, 'cancel', self.cancel)
        connect_signal(self.manual_form, 'cancel', self.cancel)

        self.form_pile = Pile(self.method_form.as_rows())

        self.bp = WidgetPlaceholder(self.method_form.buttons)

        self._select_method(None, method)

        widgets = [self.form_pile, Text(""), self.bp]
        super().__init__(
            "Edit {device} IPv{ip_version} configuration".format(
                device=device.name, ip_version=ip_version),
            widgets,
            0, 0)

    def _select_method(self, sender, method):
        rows = []

        def r(w):
            rows.append((w, self.form_pile.options('pack')))
        for row in self.method_form.as_rows():
            r(row)
        if method == 'manual':
            r(Text(""))
            for row in self.manual_form.as_rows():
                r(row)
            self.bp.original_widget = self.manual_form.buttons
        else:
            self.bp.original_widget = self.method_form.buttons
        self.form_pile.contents[:] = rows

    def done(self, sender):

        self.device.remove_ip_networks_for_version(self.ip_version)
        self.device.set_dhcp_for_version(self.ip_version, False)

        if self.method_form.method.value == "manual":
            form = self.manual_form
            # XXX this converting from and to and from strings thing is a
            # bit out of hand.
            gateway = form.gateway.value
            if gateway is not None:
                gateway = str(gateway)
            result = {
                'network': str(form.subnet.value),
                'address': str(form.address.value),
                'gateway': gateway,
                'nameservers': list(map(str, form.nameservers.value)),
                'searchdomains': form.searchdomains.value,
            }
            self.device.remove_nameservers()
            self.device.add_network(self.ip_version, result)
        elif self.method_form.method.value == "dhcp":
            self.device.set_dhcp_for_version(self.ip_version, True)
        else:
            pass
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()


class VlanForm(Form):

    def __init__(self, parent, device):
        self.parent = parent
        self.device = device
        super().__init__()

    vlan = StringField(_("VLAN ID:"))

    def clean_vlan(self, value):
        try:
            vlanid = int(value)
        except ValueError:
            vlanid = None
        if vlanid is None or vlanid < 1 or vlanid > 4095:
            raise ValueError(
                _("VLAN ID must be between 1 and 4095"))
        return vlanid

    def validate_vlan(self):
        new_name = '%s.%s' % (self.device.name, self.vlan.value)
        if new_name in self.parent.model.devices_by_name:
            return _("%s already exists") % new_name


class AddVlanStretchy(Stretchy):

    def __init__(self, parent, device):
        self.parent = parent
        self.device = device
        self.form = VlanForm(parent, device)
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)
        super().__init__(
            _('Add a VLAN tag'),
            [Pile(self.form.as_rows()), Text(""), self.form.buttons],
            0, 0)

    def done(self, sender):
        self.parent.remove_overlay()
        self.parent.controller.add_vlan(self.device, self.form.vlan.value)

    def cancel(self, sender=None):
        self.parent.remove_overlay()


class ViewInterfaceInfo(Stretchy):
    def __init__(self, parent, device):
        log.debug('ViewInterfaceInfo: {}'.format(device))
        self.parent = parent
        result = yaml.dump(device._net_info.serialize(),
                           default_flow_style=False)
        widgets = [
            Text(result),
            Text(""),
            button_pile([done_btn(_("Close"), on_press=self.close)]),
            ]
        title = _("Info for {}").format(device.name)
        super().__init__(title, widgets, 0, 2)

    def close(self, button=None):
        self.parent.remove_overlay()
