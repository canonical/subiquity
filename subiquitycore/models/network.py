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
import attr
from typing import List, Optional

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


class DHCPState(enum.Enum):
    PENDING = enum.auto()
    TIMED_OUT = enum.auto()
    RECONFIGURE = enum.auto()
    CONFIGURED = enum.auto()


@attr.s(auto_attribs=True)
class DHCPStatus:
    enabled: bool
    state: Optional[DHCPState]
    addresses: List[str]


@attr.s(auto_attribs=True)
class StaticConfig:
    addresses: List[str] = attr.Factory(list)
    gateway: Optional[str] = None
    nameservers: List[str] = attr.Factory(list)
    searchdomains: List[str] = attr.Factory(list)


@attr.s(auto_attribs=True)
class VLANConfig:
    id: int
    link: str


@attr.s(auto_attribs=True)
class WLANConfig:
    ssid: str
    psk: str


@attr.s(auto_attribs=True)
class WLANStatus:
    config: WLANConfig
    scan_state: Optional[str]
    visible_ssids: List[str]


@attr.s(auto_attribs=True)
class BondConfig:
    interfaces: List[str]
    mode: str
    xmit_hash_policy: Optional[str] = None
    lacp_rate: Optional[str] = None

    def to_config(self):
        mode = self.mode
        params = {
            'mode': self.mode,
            }
        if mode in BondParameters.supports_xmit_hash_policy:
            params['transmit-hash-policy'] = self.xmit_hash_policy
        if mode in BondParameters.supports_lacp_rate:
            params['lacp-rate'] = self.lacp_rate
        return {
            'interfaces': self.interfaces,
            'parameters': params,
            }


@attr.s(auto_attribs=True)
class NetDevInfo:
    """All the information about a NetworkDev that the view code needs."""
    name: str
    type: str

    is_connected: bool
    bond_master: Optional[str]
    is_used: bool
    disabled_reason: Optional[str]
    hwaddr: Optional[str]
    vendor: Optional[str]
    model: Optional[str]
    is_virtual: bool
    has_config: bool

    vlan: Optional[VLANConfig]
    bond: Optional[BondConfig]
    wlan: Optional[WLANConfig]

    dhcp4: DHCPStatus
    dhcp6: DHCPStatus
    static4: StaticConfig
    static6: StaticConfig

    enabled_actions: List[NetDevAction]


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

    def netdev_info(self) -> NetDevInfo:
        if self.type == 'eth':
            is_connected = self.info.is_connected
        else:
            is_connected = True
        bond_master = None
        for dev2 in self._model.get_all_netdevs():
            if dev2.type != "bond":
                continue
            if self.name in dev2.config.get('interfaces', []):
                bond_master = dev2.name
                break
        if self.type == 'bond' and self.config is not None:
            params = self.config['parameters']
            bond = BondConfig(
                interfaces=self.config['interfaces'],
                mode=params['mode'],
                xmit_hash_policy=params.get('xmit-hash-policy'),
                lacp_rate=params.get('lacp-rate'))
        else:
            bond = None
        if self.type == 'vlan' and self.config is not None:
            vlan = VLANConfig(id=self.config['id'], link=self.config['link'])
        else:
            vlan = None
        if self.type == 'wlan':
            ssid, psk = self.configured_ssid
            wlan = WLANStatus(
                config=WLANConfig(ssid=ssid, psk=psk),
                scan_state=self.info.wlan['scan_state'],
                visible_ssids=self.info.wlan['visible_ssids'])
        else:
            wlan = None

        dhcp_addresses = self.dhcp_addresses()
        configured_addresseses = {4: [], 6: []}
        if self.config is not None:
            for addr in self.config.get('addresses', []):
                configured_addresseses[addr_version(addr)].append(addr)
            ns = self.config.get('nameservers', {})
        else:
            ns = {}
        dhcp_statuses = {}
        static_configs = {}
        for v in 4, 6:
            dhcp_statuses[v] = DHCPStatus(
                enabled=self.dhcp_enabled(v),
                state=self._dhcp_state[v],
                addresses=dhcp_addresses[v])
            if self.config is not None:
                gateway = self.config.get('gateway' + str(v))
            else:
                gateway = None
            static_configs[v] = StaticConfig(
                addresses=configured_addresseses[v],
                gateway=gateway,
                nameservers=ns.get('nameservers', []),
                searchdomains=ns.get('search', []))
        return NetDevInfo(
            name=self.name,
            type=self.type,
            is_connected=is_connected,
            vlan=vlan,
            bond_master=bond_master,
            bond=bond,
            wlan=wlan,
            dhcp4=dhcp_statuses[4],
            dhcp6=dhcp_statuses[6],
            static4=static_configs[4],
            static6=static_configs[6],
            is_used=self.is_used,
            disabled_reason=self.disabled_reason,
            enabled_actions=[
                action for action in NetDevAction
                if self.supports_action(action)
                ],
            hwaddr=getattr(self.info, 'hwaddr', None),
            vendor=getattr(self.info, 'vendor', None),
            model=getattr(self.info, 'model', None),
            is_virtual=self.is_virtual,
            has_config=self.config is not None)

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
        if new_name != self.name and self.is_virtual:
            if new_name in self._model.devices_by_name:
                raise RuntimeError(
                    "renaming {old_name} over {new_name}".format(
                        old_name=self.name, new_name=new_name))
            self._model.devices_by_name[new_name] = self
            if self.info is not None:
                dead_device = NetworkDev(self._model, self.name, self.type)
                self._model.devices_by_name[self.name] = dead_device
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

    def new_vlan(self, device_name, tag):
        name = "{name}.{tag}".format(name=device_name, tag=tag)
        dev = self.devices_by_name[name] = NetworkDev(self, name, 'vlan')
        dev.config = {
            'link': device_name,
            'id': tag,
            }
        return dev

    def new_bond(self, name, bond_config):
        dev = self.devices_by_name[name] = NetworkDev(self, name, 'bond')
        dev.config = bond_config.to_config()
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
