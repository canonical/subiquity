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

import copy
import enum
import ipaddress
import logging
from socket import AF_INET, AF_INET6, if_indextoname

from subiquitycore import netplan


NETDEV_IGNORED_IFACE_NAMES = ['lo']
NETDEV_IGNORED_IFACE_TYPES = ['bridge', 'tun', 'tap', 'dummy', 'sit']
NETDEV_WHITELIST_IFACE_TYPES = ['vlan', 'bond']
log = logging.getLogger('subiquitycore.models.network')


def ip_version(ip):
    return ipaddress.ip_interface(ip).version


class NetDevAction(enum.Enum):
    INFO = _("Info")
    EDIT_WLAN = _("Edit Wifi")
    EDIT_IPV4 = _("Edit IPv4")
    EDIT_IPV6 = _("Edit IPv6")
    EDIT_BOND = _("Edit bond")
    ADD_VLAN = _("Add a VLAN tag")
    DELETE = _("Delete")


class Networkdev:
    """A Networkdev is console-conf's view of a network device.

    The view code only ever sees objects of this type.

    There are two 'sides' to a Networkdev: the state the device is
    actually in, and the device's configuration.  Where there is
    abiguity (e.g. when it comes to IP addresses), the former has
    attribute names like "actual_ip_addresses_for_version" and the
    latter has names like "configured_ip_addresses_for_version".
    """

    def __init__(self, net_info, configuration):
        self._net_info = net_info
        self._configuration = configuration
        if self.type == 'vlan':
            self._configuration['id'] = net_info.netlink_data['vlan_id']
            self._configuration['link'] = if_indextoname(
                net_info.netlink_data['vlan_link'])
        if self.type == 'bond':
            bond = self._net_info.bond
            self._configuration['interfaces'] = bond['slaves']
            params = {'mode': bond['mode']}
            if bond['mode'] in ['balance-xor', '802.3ad', 'balance-tlb']:
                params['transmit-hash-policy'] = bond['xmit_hash_policy']
            if bond['mode'] == '802.3ad':
                params['lacp-rate'] = bond['lacp_rate']
            self._configuration['parameters'] = params

    def render(self):
        if (self.configured_ip_addresses or self.dhcp4 or self.dhcp6 or
                self.is_bonded):
            return {self.name: self._configuration}
        else:
            return {}

    def supports_action(self, action):
        return getattr(self, "_supports_" + action.name)

    _supports_INFO = True
    _supports_EDIT_WLAN = property(lambda self: self.type == "wlan")
    _supports_EDIT_IPV4 = True
    _supports_EDIT_IPV6 = True
    _supports_EDIT_BOND = property(lambda self: self.is_bond_master)
    _supports_ADD_VLAN = property(
        lambda self: self.type != "vlan"
        and not self._net_info.bond['is_slave'])
    _supports_DELETE = property(lambda self: self.is_virtual)

    @property
    def configured(self):
        if self.configured_ip_addresses or self.dhcp4 or self.dhcp6:
            return True
        return False

    @property
    def name(self):
        return self._net_info.name

    @property
    def ifindex(self):
        return self._net_info.ifindex

    @property
    def type(self):
        return self._net_info.type

    @property
    def hwaddr(self):
        return self._net_info.hwaddr

    @property
    def vendor(self):
        return self._net_info.vendor

    @property
    def model(self):
        return self._net_info.model

    @property
    def is_connected(self):
        return self._net_info.is_connected

    @property
    def is_bond_slave(self):
        return self._net_info.bond['is_slave']

    @property
    def is_bond_master(self):
        return self._net_info.bond['is_master']

    @property
    def is_bonded(self):
        return self.is_bond_master or self.is_bond_slave

    @property
    def is_virtual(self):
        return self._net_info.is_virtual

    @property
    def speed(self):
        '''string'ify and bucketize iface speed:
           1M, 10M, 1G, 10G, 40G, 100G
        '''
        hwattr = self._net_info.udev_data['attrs']
        speed = hwattr.get('speed', 0)
        if not speed:
            return None

        speed = int(speed)
        if speed < 1000:
            return "{}M".format(speed)

        return "{}G".format(int(speed / 1000))

    def dhcp_for_version(self, version):
        dhcp_key = 'dhcp%s' % version
        return self._configuration.get(dhcp_key, False)

    def set_dhcp_for_version(self, version, val):
        dhcp_key = 'dhcp%s' % version
        self._configuration[dhcp_key] = val

    @property
    def dhcp4(self):
        return self._configuration.get('dhcp4', False)

    @dhcp4.setter
    def dhcp4(self, val):
        if val:
            self._configuration['dhcp4'] = val
        else:
            self._configuration.pop('dhcp4', None)

    @property
    def dhcp6(self):
        return self._configuration.get('dhcp6', False)

    @dhcp6.setter
    def dhcp6(self, val):
        if val:
            self._configuration['dhcp6'] = val
        else:
            self._configuration.pop('dhcp6', None)

    def actual_ip_addresses_for_version(self, version):
        if version == 4:
            fam = AF_INET
        elif version == 6:
            fam = AF_INET6
        return [addr.ip for _, addr in sorted(self._net_info.addresses.items())
                if addr.family == fam]

    @property
    def actual_ip_addresses(self):
        return (self.actual_ip_addresses_for_version(4) +
                self.actual_ip_addresses_for_version(6))

    def configured_ip_addresses_for_version(self, version):
        r = []
        for ip in self._configuration.get('addresses', []):
            if ip_version(ip) == version:
                r.append(ip)
        return r

    @property
    def actual_global_ip_addresses(self):
        return [addr.ip for _, addr in sorted(self._net_info.addresses.items())
                if addr.scope == "global"]

    @property
    def configured_ip_addresses(self):
        return self._configuration.setdefault('addresses', [])

    def configured_gateway_for_version(self, version):
        return self._configuration.get('gateway%s' % version, None)

    def set_configured_gateway_for_version(self, version, gateway):
        key = 'gateway%s' % version
        if gateway is None:
            self._configuration.pop(key, None)
        else:
            self._configuration[key] = gateway

    @property
    def configured_nameservers(self):
        ns = self._configuration.setdefault('nameservers', {})
        return ns.setdefault('addresses', [])

    @property
    def configured_searchdomains(self):
        ns = self._configuration.setdefault('nameservers', {})
        return ns.setdefault('search', [])

    @property
    def actual_ssid(self):
        if self._net_info.ssid:
            return self._net_info.ssid
        else:
            return None

    @property
    def actual_ssids(self):
        return self._net_info.wlan['visible_ssids']

    @property
    def scan_state(self):
        return self._net_info.wlan['scan_state']

    @property
    def configured_ssid(self):
        aps = list(self._configuration.get('access-points', {}).keys())
        if len(aps) > 0:
            return aps[0]
        else:
            return None

    @property
    def configured_wifi_psk(self):
        aps = list(self._configuration.get('access-points', {}).keys())
        if len(aps) > 0:
            ap = self._configuration.get('access-points', {})[aps[0]]
            return ap.get('password')
        else:
            return None

    def set_ssid_psk(self, ssid, psk):
        aps = self._configuration.setdefault('access-points', {})
        aps.clear()
        if ssid is not None:
            aps[ssid] = {}
            if psk is not None:
                aps[ssid]['password'] = psk

    def remove_networks(self):
        self.remove_ip_networks_for_version(4)
        self.remove_ip_networks_for_version(6)

    def remove_ip_networks_for_version(self, version):
        dhcp_key = 'dhcp%s' % version
        setattr(self, dhcp_key, False)
        addrs = []
        for ip in self._configuration.get('addresses', []):
            if ip_version(ip) != version:
                addrs.append(ip)
        self._configuration['addresses'] = addrs
        self.set_configured_gateway_for_version(version, None)

    def remove_nameservers(self):
        self._configuration['nameservers'] = {}

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
        self.configured_ip_addresses.append(address)
        self.set_configured_gateway_for_version(version, network['gateway'])
        self.configured_nameservers.extend(network['nameservers'])
        self.configured_searchdomains.extend(network['searchdomains'])


def valid_ipv4_address(addr):
    try:
        ip = ipaddress.IPv4Address(addr)
    except ipaddress.AddressValueError:
        return False

    return ip


def _sanitize_inteface_config(iface_config):
    for ap, ap_config in iface_config.get('access-points', {}).items():
        if 'password' in ap_config:
            ap_config['password'] = '<REDACTED>'


def sanitize_interface_config(iface_config):
    iface_config = copy.deepcopy(iface_config)
    _sanitize_inteface_config(iface_config)
    return iface_config


def sanitize_config(config):
    """Return a copy of config with passwords redacted."""
    config = copy.deepcopy(config)
    interfaces = config.get('network', {}).get('wifis', {}).items()
    for iface, iface_config in interfaces:
        _sanitize_inteface_config(iface_config)
    return config


class NetworkModel(object):
    """ Model representing network interfaces
    """
    additional_options = []

    def __init__(self, support_wlan=True):
        self.support_wlan = support_wlan
        self.devices = {}  # Maps ifindex to Networkdev
        self.devices_by_name = {}  # Maps interface names to Networkdev
        self.default_v4_gateway = None
        self.default_v6_gateway = None
        self.v4_gateway_dev = None
        self.v6_gateway_dev = None
        self.network_routes = {}

    def parse_netplan_configs(self, netplan_root):
        config = netplan.Config()
        config.load_from_root(netplan_root)
        self.config = config

    def get_menu(self):
        return self.additional_options

    def new_link(self, ifindex, link):
        if link.type in NETDEV_IGNORED_IFACE_TYPES:
            return
        if not self.support_wlan and link.type == "wlan":
            return
        if link.name in NETDEV_IGNORED_IFACE_NAMES:
            return
        if link.is_virtual and link.type not in NETDEV_WHITELIST_IFACE_TYPES:
            return
        config = self.config.config_for_device(link)
        log.debug("new_link %s %s with config %s",
                  ifindex, link.name, sanitize_interface_config(config))
        netdev = Networkdev(link, config)
        self.devices[ifindex] = netdev
        self.devices_by_name[link.name] = netdev
        return netdev

    def update_link(self, ifindex):
        # This is pretty edge-casey as the fact that we wait for the
        # udev queue to settle should mean we never see an interface
        # be renamed. But just in case...
        if ifindex not in self.devices:
            return
        dev = self.devices[ifindex]
        for k, v in self.devices_by_name.items():
            if v.ifindex == ifindex and k != dev.name:
                log.debug("link renamed %s -> %s", k, dev.name)
                del self.devices_by_name[k]
                self.devices_by_name[dev.name] = dev
                break
        return dev

    def del_link(self, ifindex):
        if ifindex in self.devices:
            dev = self.devices[ifindex]
            del self.devices_by_name[dev.name]
            del self.devices[ifindex]
            return dev

    def get_all_netdevs(self):
        return [v for k, v in sorted(self.devices_by_name.items())]

    def get_configured_interfaces(self):
        return [dev for dev in self.get_all_netdevs() if dev.configured]

    def get_netdev_by_name(self, name):
        return self.devices_by_name[name]

    def clear_gateways(self):
        log.debug("clearing default gateway")
        self.default_v4_gateway = None
        self.default_v6_gateway = None

    def set_default_v4_gateway(self, ifname, gateway_input):
        if gateway_input is None:
            self.default_v4_gateway = None
            self.v4_gateway_dev = None
            return

        addr = valid_ipv4_address(gateway_input)
        if addr is False:
            raise ValueError(('Invalid gateway IP ') + gateway_input)

        self.default_v4_gateway = addr.compressed
        self.v4_gateway_dev = ifname

    def set_default_v6_gateway(self, ifname, gateway_input):
        if gateway_input is None:
            self.default_v6_gateway = None
            self.v6_gateway_dev = None
            return

        # FIXME: validate v6 address.
        self.default_v6_gateway = gateway_input
        self.v6_gateway_dev = ifname

    def render(self):
        config = {
            'network': {
                'version': 2,
            },
        }
        ethernets = {}
        bonds = {}
        wifis = {}
        vlans = {}
        for dev in self.devices.values():
            if dev.type == 'eth':
                ethernets.update(dev.render())
            if dev.type == 'bond':
                bonds.update(dev.render())
            if dev.type == 'wlan':
                wifis.update(dev.render())
            if dev.type == 'vlan':
                vlans.update(dev.render())
        if any(ethernets):
            config['network']['ethernets'] = ethernets
        if any(bonds):
            config['network']['bonds'] = bonds
        if any(wifis):
            config['network']['wifis'] = wifis
        if any(vlans):
            config['network']['vlans'] = vlans

        nw_routes = []
        if self.default_v4_gateway:
            nw_routes.append(
                {'to': '0.0.0.0/0', 'via': self.default_v4_gateway})
        if self.default_v6_gateway is not None:
            nw_routes.append({'to': '::/0', 'via': self.default_v6_gateway})
        if len(nw_routes) > 0:
            config['network']['routes'] = nw_routes

        return config
