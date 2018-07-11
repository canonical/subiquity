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
    CheckBox,
    connect_signal,
    Text,
    WidgetPlaceholder,
    )

from subiquitycore.ui.container import Pile, WidgetWrap
from subiquitycore.ui.form import (
    ChoiceField,
    Form,
    FormField,
    simple_field,
    StringField,
    WantsToKnowFormField,
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
        self.parent.update_link(self.device)
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


_bond_modes = [
    ('balance-rr', True, 'balance-rr'),
    ('active-backup', True, 'active-backup'),
    ('balance-xor', True, 'balance-xor'),
    ('broadcast', True, 'broadcast'),
    ('802.3ad', True, '802.3ad'),
    ('balance-tlb', True, 'balance-tlb'),
    ('balance-alb', True, 'balance-alb'),
]


_supports_xmit_hash_policy = {
    'balance-xor',
    '802.3ad',
    'balance-tlb',
}


_xmit_hash_policies = [
    ('layer2', True, 'layer2'),
    ('layer2+3', True, 'layer2+3'),
    ('layer3+4', True, 'layer3+4'),
    ('encap2+3', True, 'encap2+3'),
    ('encap3+4', True, 'encap3+4'),
]


_supports_lacp_rate = {
    '802.3ad',
}


_lacp_rates = [
    ('slow', True, 'slow'),
    ('fast', True, 'fast'),
]


class MultiNetdevChooser(WidgetWrap, WantsToKnowFormField):

    def __init__(self):
        self.pile = Pile([])
        self.selected = set()
        self.box_to_device = {}
        super().__init__(self.pile)

    @property
    def value(self):
        return list(sorted(self.selected, key=lambda x: x.name))

    @value.setter
    def value(self, value):
        self.selected = set(value)
        for checkbox, opt in self.pile.contents:
            checkbox.state = self.box_to_device[checkbox] in self.selected

    def set_bound_form_field(self, bff):
        contents = []
        for d in bff.form.candidate_netdevs:
            box = CheckBox(d.name, on_state_change=self._state_change)
            self.box_to_device[box] = d
            contents.append((box, self.pile.options('pack')))
        self.pile.contents[:] = contents

    def _state_change(self, sender, state):
        device = self.box_to_device[sender]
        if state:
            self.selected.add(device)
        else:
            self.selected.remove(device)


MultiNetdevField = simple_field(MultiNetdevChooser)
MultiNetdevField.takes_default_style = False


class BondForm(Form):

    def __init__(self, initial, candidate_netdevs, all_netdev_names):
        self.candidate_netdevs = candidate_netdevs
        self.all_netdev_names = all_netdev_names
        super().__init__(initial)
        connect_signal(self.mode.widget, 'select', self._select_level)
        self._select_level(None, self.mode.value)

    name = StringField(_("Name:"))
    devices = MultiNetdevField(_("Devices: "))
    mode = ChoiceField(_("Bond mode:"), choices=_bond_modes)
    xmit_hash_policy = ChoiceField(
        _("XMIT hash policy:"), choices=_xmit_hash_policies)
    lacp_rate = ChoiceField(_("LACP rate:"), choices=_lacp_rates)
    ok_label = _("Save")

    def _select_level(self, sender, new_value):
        self.xmit_hash_policy.enabled = new_value in _supports_xmit_hash_policy
        self.lacp_rate.enabled = new_value in _supports_lacp_rate

    def validate_name(self):
        name = self.name.value
        if name in self.all_netdev_names:
            return _(
                'There is already a network device named "{}"'
                ).format(name)
        if len(name) == 0:
            return _("Name cannot be empty")
        if len(name) > 16:
            return _("Name cannot be more than 16 characters long")


class BondStretchy(Stretchy):

    def __init__(self, parent, existing=None):
        self.parent = parent
        self.existing = existing
        all_netdev_names = {
            device.name for device in parent.model.get_all_netdevs()}
        if existing is None:
            title = _('Create bond')
            x = 0
            while True:
                name = 'bond{}'.format(x)
                if name not in all_netdev_names:
                    break
                x += 1
            initial = {
                'devices': set(),
                'name': name,
                }
        else:
            title = _('Edit bond')
            all_netdev_names.remove(existing.name)
            params = existing._configuration['parameters']
            mode = params['mode']
            initial = {
                'devices': set([
                    parent.model.get_netdev_by_name(name)
                    for name in existing._configuration['interfaces']]),
                'name': existing.name,
                'mode': mode,
                }
            if mode in _supports_xmit_hash_policy:
                initial['xmit_hash_policy'] = params['transmit-hash-policy']
            if mode in _supports_lacp_rate:
                initial['lacp_rate'] = params['lacp-rate']

        def device_ok(device):
            if device is existing:
                return False
            if device in initial['devices']:
                return True
            return not device.is_bond_slave

        candidate_netdevs = [
            device  for device in parent.model.get_all_netdevs()
            if device_ok(device)]

        self.form = BondForm(initial, candidate_netdevs, all_netdev_names)
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)
        super().__init__(
            title,
            [Pile(self.form.as_rows()), Text(""), self.form.buttons],
            0, 0)

    def done(self, sender):
        if self.existing is not None:
            self.parent.controller.rm_virtual_interface(self.existing)
        self.parent.controller.add_bond(self.form.as_data())
        for slave in self.form.devices.value:
            self.parent.controller.add_master(
                slave, master_name=self.form.name.value)
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()
