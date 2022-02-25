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

from urwid import (
    CheckBox,
    connect_signal,
    Text,
    WidgetPlaceholder,
    )

from subiquitycore.models.network import (
    BondConfig,
    BondParameters,
    StaticConfig,
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
    'subiquitycore.ui.views.network_configure_manual_interface')

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
        if '/' not in subnet:
            if self.ip_version == 4:
                example = "xx.xx.xx.xx/yy"
            else:
                example = "xx:xx:..:xx/yy"
            raise ValueError(_("should be in CIDR form ({example})").format(
                example=example))
        return self.ip_network_cls(subnet)

    def clean_address(self, address):
        address = self.ip_address_cls(address)
        try:
            subnet = self.subnet.value
        except ValueError:
            return
        if address not in subnet:
            raise ValueError(
                _("'{address}' is not contained in '{subnet}'").format(
                    address=address, subnet=subnet)
                )
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
    # A choice for how to configure a network interface
    (_("Automatic (DHCP)"), True, "dhcp"),
    # A choice for how to configure a network interface
    (_("Manual"), True, "manual"),
    # A choice for how to configure a network interface
    (_("Disabled"), True, "disable"),
    ]


class NetworkMethodForm(Form):
    ok_label = _("Save")
    method = ChoiceField("IPv{ip_version} Method: ", choices=network_choices)


class EditNetworkStretchy(Stretchy):

    def __init__(self, parent, dev_info, ip_version):
        self.parent = parent
        self.dev_info = dev_info
        self.ip_version = ip_version

        self.method_form = NetworkMethodForm()
        self.method_form.method.caption = _(
            "IPv{v} Method: ").format(v=ip_version)
        manual_initial = {}
        dhcp_status = getattr(dev_info, 'dhcp' + str(ip_version))
        static_config = getattr(dev_info, 'static' + str(ip_version))
        if static_config.addresses:
            method = 'manual'
            addr = ipaddress.ip_interface(static_config.addresses[0])
            manual_initial = {
                'subnet': str(addr.network),
                'address': str(addr.ip),
                'nameservers': ', '.join(static_config.nameservers),
                'searchdomains': ', '.join(static_config.searchdomains),
            }
            if static_config.gateway:
                manual_initial['gateway'] = static_config.gateway
        elif dhcp_status.enabled:
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
            "Edit {device} IPv{v} configuration".format(
                device=dev_info.name, v=ip_version),
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
        if self.method_form.method.value == "manual":
            form = self.manual_form
            # XXX this converting from and to and from strings thing is a
            # bit out of hand.
            gateway = form.gateway.value
            if gateway is not None:
                gateway = str(gateway)
            address = str(form.address.value).split('/')[0]
            address += '/' + str(form.subnet.value).split('/')[1]
            config = StaticConfig(
                addresses=[address],
                gateway=gateway,
                nameservers=list(map(str, form.nameservers.value)),
                searchdomains=form.searchdomains.value)
            log.debug(
                "EditNetworkStretchy %s manual config=%s",
                self.ip_version, config)
            self.parent.controller.set_static_config(
                self.dev_info.name, self.ip_version, config)
        elif self.method_form.method.value == "dhcp":
            self.parent.controller.enable_dhcp(
                self.dev_info.name, self.ip_version)
            log.debug("EditNetworkStretchy %s, dhcp", self.ip_version)
        else:
            self.parent.controller.disable_network(
                self.dev_info.name, self.ip_version)
            log.debug("EditNetworkStretchy %s, disabled", self.ip_version)
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()


class VlanForm(Form):

    ok_label = _("Create")

    def __init__(self, parent, dev_name):
        self.parent = parent
        self.dev_name = dev_name
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
        new_name = '%s.%s' % (self.dev_name, self.vlan.value)
        if new_name in self.parent.cur_netdev_names:
            return _("{netdev} already exists").format(netdev=new_name)


class AddVlanStretchy(Stretchy):

    def __init__(self, parent, dev_info):
        self.parent = parent
        self.dev_name = dev_info.name
        self.form = VlanForm(parent, self.dev_name)
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)
        super().__init__(
            _('Add a VLAN tag'),
            [Pile(self.form.as_rows()), Text(""), self.form.buttons],
            0, 0)

    def done(self, sender):
        log.debug(
            "AddVlanStretchy.done %s %s",
            self.dev_name, self.form.vlan.value)
        self.parent.controller.add_vlan(
            self.dev_name, self.form.vlan.value)
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()


class ViewInterfaceInfo(Stretchy):
    def __init__(self, parent, name, nic_info):
        self.parent = parent
        widgets = [
            Text(nic_info),
            Text(""),
            button_pile([done_btn(_("Close"), on_press=self.close)]),
            ]
        # {device} is the name of a network device
        title = _("Info for {device}").format(device=name)
        super().__init__(title, widgets, 0, 2)

    def close(self, button=None):
        self.parent.remove_overlay()


class MultiNetdevChooser(WidgetWrap, WantsToKnowFormField):

    def __init__(self):
        self.pile = Pile([])
        self.selected = set()
        self.box_to_device = {}
        super().__init__(self.pile)

    @property
    def value(self):
        return list(sorted(self.selected))

    @value.setter
    def value(self, value):
        self.selected = set(value)
        for checkbox, opt in self.pile.contents:
            checkbox.state = self.box_to_device[checkbox] in self.selected

    def set_bound_form_field(self, bff):
        contents = []
        for d in bff.form.candidate_netdevs:
            box = CheckBox(d, on_state_change=self._state_change)
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
    interfaces = MultiNetdevField(_("Devices: "))
    mode = ChoiceField(_("Bond mode:"), choices=BondParameters.modes)
    xmit_hash_policy = ChoiceField(
        _("XMIT hash policy:"), choices=BondParameters.xmit_hash_policies)
    lacp_rate = ChoiceField(_("LACP rate:"), choices=BondParameters.lacp_rates)
    ok_label = _("Save")

    def _select_level(self, sender, new_value):
        self.xmit_hash_policy.enabled = (
            new_value in BondParameters.supports_xmit_hash_policy)
        self.lacp_rate.enabled = (
            new_value in BondParameters.supports_lacp_rate)

    def validate_name(self):
        name = self.name.value
        if name in self.all_netdev_names:
            return _(
                'There is already a network device named "{netdev}"'
                ).format(netdev=name)
        if len(name) == 0:
            return _("Name cannot be empty")
        if len(name) > 16:
            return _("Name cannot be more than 16 characters long")


class BondStretchy(Stretchy):

    def __init__(self, parent, existing_bond_info, candidate_names):
        self.parent = parent
        all_netdev_names = set(parent.cur_netdev_names)
        if existing_bond_info is None:
            self.existing_name = None
            title = _('Create bond')
            label = _("Create")
            x = 0
            while True:
                name = 'bond{}'.format(x)
                if name not in all_netdev_names:
                    break
                x += 1
            initial = {
                'interfaces': [],
                'name': name,
                }
        else:
            self.existing_name = existing_bond_info.name
            bondconfig = existing_bond_info.bond
            title = _('Edit bond')
            label = _("Save")
            all_netdev_names.remove(self.existing_name)
            mode = bondconfig.mode
            initial = {
                'interfaces': bondconfig.interfaces,
                'name': self.existing_name,
                'mode': mode,
                }
            if mode in BondParameters.supports_xmit_hash_policy:
                initial['xmit_hash_policy'] = bondconfig.xmit_hash_policy
            if mode in BondParameters.supports_lacp_rate:
                initial['lacp_rate'] = bondconfig.lacp_rate

        candidate_names = sorted(candidate_names + initial['interfaces'])

        self.form = BondForm(initial, candidate_names, all_netdev_names)
        self.form.buttons.base_widget[0].set_label(label)
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)
        super().__init__(
            title,
            [Pile(self.form.as_rows()), Text(""), self.form.buttons],
            0, 0)

    def done(self, sender):
        result = self.form.as_data()
        log.debug("BondStretchy.done result=%s", result)
        new_name = result.pop('name')
        new_config = BondConfig(**result)
        self.parent.controller.add_or_update_bond(
            self.existing_name, new_name, new_config)
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()
