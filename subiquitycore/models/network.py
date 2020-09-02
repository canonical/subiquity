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

import enum
import ipaddress
import logging
import yaml
from socket import AF_INET, AF_INET6

from subiquitycore.gettext38 import pgettext
from subiquitycore import netplan


NETDEV_IGNORED_IFACE_TYPES = [
    'lo', 'bridge', 'tun', 'tap', 'dummy', 'sit', 'can', '???'
]
NETDEV_ALLOWED_VIRTUAL_IFACE_TYPES = ['vlan', 'bond']


log = logging.getLogger('subiquitycore.models.network')


def addr_version(ip):
    return ipaddress.ip_interface(ip).version


class NetDevAction(enum.Enum):
    # Information about a network interface
    INFO = pgettext("NetDevAction", "Info")
    EDIT_WLAN = pgettext("NetDevAction", "Edit Wifi")
    EDIT_IPV4 = pgettext("NetDevAction", "Edit IPv4")
    EDIT_IPV6 = pgettext("NetDevAction", "Edit IPv6")
    EDIT_BOND = pgettext("NetDevAction", "Edit bond")
    ADD_VLAN = pgettext("NetDevAction", "Add a VLAN tag")
    DELETE = pgettext("NetDevAction", "Delete")

    def str(self):
        return pgettext(type(self).__name__, self.value)


class BondParameters:
    # Just a place to hang various data about how bonds can be
    # configured.

    modes = [
        'balance-rr',
        'active-backup',
        'balance-xor',
        'broadcast',
        '802.3ad',
        'balance-tlb',
        'balance-alb',
    ]

    supports_xmit_hash_policy = {
        'balance-xor',
        '802.3ad',
        'balance-tlb',
    }

    xmit_hash_policies = [
        'layer2',
        'layer2+3',
        'layer3+4',
        'encap2+3',
        'encap3+4',
    ]

    supports_lacp_rate = {
        '802.3ad',
    }

    lacp_rates = [
        'slow',
        'fast',
    ]


class NetworkDev(object):

    def __init__(self, model, name, typ):
        self._model = model
        self._name = name
        self.type = typ
        self.config = {}
        self.info = None
        self.disabled_reason = None
        self.dhcp_events = {}
        self._dhcp_state = {
            4: None,
            6: None,
            }

    def dhcp_addresses(self):
        r = {4: [], 6: []}
        if self.info is not None:
            for a in self.info.addresses.values():
                if a.family == AF_INET:
                    v = 4
                elif a.family == AF_INET6:
                    v = 6
                else:
                    continue
                if a.source == 'dhcp':
                    r[v].append(str(a.address))
        return r

    def dhcp_enabled(self, version):
        if self.config is None:
            return False
        else:
            return self.config.get('dhcp{v}'.format(v=version), False)

    def dhcp_state(self, version):
        if not self.config.get('dhcp{v}'.format(v=version), False):
            return None
        return self._dhcp_state[version]

    def set_dhcp_state(self, version, state):
        self._dhcp_state[version] = state

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_name):
        # If a virtual device that already exists is renamed, we need
        # to create a dummy NetworkDev so that the existing virtual
        # device is actually deleted when the config is applied.
        if new_name != self.name and self.is_virtual and self.info is not None:
            if new_name in self.model.devices_by_name:
                raise RuntimeError(
                    "renaming {old_name} over {new_name}".format(
                        old_name=self.name, new_name=new_name))
            self._model.devices_by_name[new_name] = self
            dead_device = self._model.devices_by_name[self.name] = NetworkDev(
                self.name, self.type)
            dead_device.config = None
            dead_device.info = self.info
            self.info = None
        self._name = new_name

    def supports_action(self, action):
        return getattr(self, "_supports_" + action.name)

    @property
    def configured_ssid(self):
        for ssid, settings in self.config.get('access-points', {}).items():
            psk = settings.get('password')
            return ssid, psk
        return None, None

    def set_ssid_psk(self, ssid, psk):
        aps = self.config.setdefault('access-points', {})
        aps.clear()
        if ssid is not None:
            aps[ssid] = {}
            if psk is not None:
                aps[ssid]['password'] = psk

    @property
    def ifindex(self):
        if self.info is not None:
            return self.info.ifindex
        else:
            return None

    @property
    def is_virtual(self):
        return self.type in NETDEV_ALLOWED_VIRTUAL_IFACE_TYPES

    @property
    def is_bond_slave(self):
        for dev in self._model.get_all_netdevs():
            if dev.type == "bond":
                if self.name in dev.config.get('interfaces', []):
                    return True
        return False

    @property
    def is_used(self):
        for dev in self._model.get_all_netdevs():
            if dev.type == "bond":
                if self.name in dev.config.get('interfaces', []):
                    return True
            if dev.type == "vlan":
                if self.name == dev.config.get('link'):
                    return True
        return False

    @property
    def actual_global_ip_addresses(self):
        return [addr.ip for _, addr in sorted(self.info.addresses.items())
                if addr.scope == "global"]

    _supports_INFO = True
    _supports_EDIT_WLAN = property(lambda self: self.type == "wlan")
    _supports_EDIT_IPV4 = True
    _supports_EDIT_IPV6 = True
    _supports_EDIT_BOND = property(lambda self: self.type == "bond")
    _supports_ADD_VLAN = property(
        lambda self: self.type != "vlan" and not self.is_bond_slave)
    _supports_DELETE = property(
        lambda self: self.is_virtual and not self.is_used)

    def remove_ip_networks_for_version(self, version):
        self.config.pop('dhcp{v}'.format(v=version), None)
        self.config.pop('gateway{v}'.format(v=version), None)
        addrs = []
        for ip in self.config.get('addresses', []):
            if addr_version(ip) != version:
                addrs.append(ip)
        if addrs:
            self.config['addresses'] = addrs
        else:
            self.config.pop('addresses', None)

    def add_network(self, version, network):
        # result = {
        #    'network': self.subnet_input.value,
        #    'address': self.address_input.value,
        #    'gateway': self.gateway_input.value,
        #    'nameserver': [nameservers],
        #    'searchdomains': [searchdomains],
        # }
        address = network['address'].split('/')[0]
        address += '/' + network['network'].split('/')[1]
        self.config.setdefault('addresses', []).append(address)
        gwkey = 'gateway{v}'.format(v=version)
        if network['gateway']:
            self.config[gwkey] = network['gateway']
        else:
            self.config.pop(gwkey, None)
        ns = self.config.setdefault('nameservers', {})
        if network['nameservers']:
            ns.setdefault('addresses', []).extend(network['nameservers'])
        if network['searchdomains']:
            ns.setdefault('search', []).extend(network['searchdomains'])


class NetworkModel(object):
    """ """

    def __init__(self, project, support_wlan=True):
        self.support_wlan = support_wlan
        self.devices_by_name = {}  # Maps interface names to NetworkDev
        self.has_network = False
        self.project = project

    def parse_netplan_configs(self, netplan_root):
        self.config = netplan.Config()
        self.config.load_from_root(netplan_root)

    def new_link(self, ifindex, link):
        log.debug("new_link %s %s %s", ifindex, link.name, link.type)
        if link.type in NETDEV_IGNORED_IFACE_TYPES:
            return
        if not self.support_wlan and link.type == "wlan":
            return
        if link.is_virtual and (
                link.type not in NETDEV_ALLOWED_VIRTUAL_IFACE_TYPES):
            return
        dev = self.devices_by_name.get(link.name)
        if dev is not None:
            # XXX What to do if types don't match??
            if dev.info is not None:
                # This shouldn't happen! No sense getting too upset
                # about if it does though.
                pass
            else:
                dev.info = link
        else:
            config = self.config.config_for_device(link)
            if link.is_virtual and not config:
                # If we see a virtual device without there already
                # being a config for it, we just ignore it.
                return
            dev = NetworkDev(self, link.name, link.type)
            dev.info = link
            dev.config = config
            log.debug("new_link %s %s with config %s",
                      ifindex, link.name,
                      netplan.sanitize_interface_config(dev.config))
            self.devices_by_name[link.name] = dev
        return dev

    def update_link(self, ifindex):
        for name, dev in self.devices_by_name.items():
            if dev.ifindex == ifindex:
                return dev

    def del_link(self, ifindex):
        for name, dev in self.devices_by_name.items():
            if dev.ifindex == ifindex:
                dev.info = None
                if dev.is_virtual:
                    # We delete all virtual devices before running netplan
                    # apply.  If a device has been deleted in the UI, we set
                    # dev.config to None.  Now it's actually gone, forget we
                    # ever knew it existed.
                    if dev.config is None:
                        del self.devices_by_name[name]
                else:
                    # If a physical interface disappears on us, it's gone.
                    del self.devices_by_name[name]
                return dev

    def new_vlan(self, device, tag):
        name = "{name}.{tag}".format(name=device.name, tag=tag)
        dev = self.devices_by_name[name] = NetworkDev(self, name, 'vlan')
        dev.config = {
            'link': device.name,
            'id': tag,
            }
        return dev

    def new_bond(self, name, interfaces, params):
        dev = self.devices_by_name[name] = NetworkDev(self, name, 'bond')
        dev.config = {
            'interfaces': interfaces,
            'parameters': params,
            }
        return dev

    def get_all_netdevs(self, include_deleted=False):
        devs = [v for k, v in sorted(self.devices_by_name.items())]
        if not include_deleted:
            devs = [v for v in devs if v.config is not None]
        return devs

    def get_netdev_by_name(self, name):
        return self.devices_by_name[name]

    def stringify_config(self, config):
        return '\n'.join([
            "# This is the network config written by '{}'".format(
                self.project),
            yaml.dump(config, default_flow_style=False),
            ])

    def render_config(self):
        config = {
            'network': {
                'version': 2,
            },
        }
        type_to_key = {
            'eth': 'ethernets',
            'bond': 'bonds',
            'wlan': 'wifis',
            'vlan': 'vlans',
            }
        for dev in self.get_all_netdevs():
            key = type_to_key[dev.type]
            configs = config['network'].setdefault(key, {})
            if dev.config or dev.is_used:
                configs[dev.name] = dev.config

        return config

    def render(self):
        return {
            'write_files': {
                'etc_netplan_installer': {
                    'path': 'etc/netplan/00-installer-config.yaml',
                    'content': self.stringify_config(self.render_config()),
                    },
                'nonet': {
                    'path': ('etc/cloud/cloud.cfg.d/'
                             'subiquity-disable-cloudinit-networking.cfg'),
                    'content': 'network: {config: disabled}\n',
                    },
                },
            }
