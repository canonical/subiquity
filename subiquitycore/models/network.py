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
import fnmatch
import glob
import ipaddress
import logging
import os
from socket import AF_INET, AF_INET6

import yaml, yaml.reader


NETDEV_IGNORED_IFACE_NAMES = ['lo']
NETDEV_IGNORED_IFACE_TYPES = ['bridge', 'tun', 'tap', 'dummy', 'sit']
log = logging.getLogger('subiquitycore.models.network')


class _NetplanDevice:
    def __init__(self, name, config):
        match = config.get('match')
        if match is None:
            self.match_name = name
            self.match_mac = None
            self.match_driver = None
        else:
            self.match_name = match.get('name')
            self.match_mac = match.get('macaddress')
            self.match_driver = match.get('driver')
        self.config = config

    def matches_link(self, link):
        if self.match_name is not None:
            matches_name = fnmatch.fnmatch(link.name, self.match_name)
        else:
            matches_name = True
        if self.match_mac is not None:
            matches_mac = self.match_mac == link.hwaddr
        else:
            matches_mac = True
        if self.match_driver is not None:
            matches_driver = self.match_driver == link.driver
        else:
            matches_driver = True
        return matches_name and matches_mac and matches_driver


class NetplanConfig:
    """A NetplanConfig represents the network config for a system.

    Call parse_netplan_config() with each piece of yaml config, and then
    call config_for_device to get the config that matches a particular
    network devices, if any.
    """

    def __init__(self):
        self.devices = []

    def parse_netplan_config(self, config):
        try:
            config = yaml.safe_load(config)
        except yaml.reader.ReaderError as e:
            log.info("could not parse config: %s", e)
            return
        network = config.get('network')
        if network is None:
            log.info("no 'network' key in config")
            return
        version = network.get("version")
        if version != 2:
            log.info("network has no/unexpected version %s", version)
            return
        for ethernet, eth_config in network.get('ethernets', {}).items():
            self.devices.append(_NetplanDevice(ethernet, eth_config))
        for wifi, wifi_config in network.get('wifis', {}).items():
            self.devices.append(_NetplanDevice(wifi, wifi_config))

    def config_for_device(self, link):
        for dev in self.devices:
            if dev.matches_link(link):
                config = copy.deepcopy(dev.config)
                if 'match' in config:
                    del config['match']
                return config
        else:
            return {}


def ip_version(ip):
    return ipaddress.ip_interface(ip).version


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

    def render(self):
        if self.configured_ip_addresses or self.dhcp4 or self.dhcp6:
            return {self.name: self._configuration}
        else:
            return {}

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
        return self._net_info.vendor

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
        dhcp_key = 'dhcp%s'%(version,)
        return self._configuration.get(dhcp_key, False)

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
        return [addr.ip for _, addr in sorted(self._net_info.addresses.items()) if addr.family == fam]

    @property
    def actual_ip_addresses(self):
        return self.actual_ip_addresses_for_version(4) + self.actual_ip_addresses_for_version(6)

    def configured_ip_addresses_for_version(self, version):
        r = []
        for ip in self._configuration.get('addresses', []):
            if ip_version(ip) == version:
                r.append(ip)
        return r

    @property
    def actual_global_ip_addresses(self):
        return [addr.ip for _, addr in sorted(self._net_info.addresses.items()) if addr.scope == "global"]

    @property
    def configured_ip_addresses(self):
        return self._configuration.setdefault('addresses', [])

    def configured_gateway_for_version(self, version):
        return self._configuration.get('gateway%s'%(version,), None)

    def set_configured_gateway_for_version(self, version, gateway):
        key = 'gateway%s'%(version,)
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
            return self._net_info.ssid.decode('utf-8', 'replace')
        else:
            return None

    @property
    def actual_ssids(self):
        return [ssid.decode('utf-8', 'replace') for ssid in self._net_info.ssids]

    @property
    def scan_state(self):
        return self._net_info.scan_state

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
        dhcp_key = 'dhcp%s'%(version,)
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


class NetworkModel(object):
    """ Model representing network interfaces
    """

    additional_options = [
        #('Set a custom IPv4 default route', 'menu:network:main:set-default-v4-route'),
        #('Set a custom IPv6 default route', 'menu:network:main:set-default-v6-route'),
        #('Bond interfaces',                 'menu:network:main:bond-interfaces'),
        #('Install network driver',          'network:install-network-driver'),
    ]

    # TODO: what is "linear" level?
    bonding_modes = {
        0: 'balance-rr',
        1: 'active-backup',
        2: 'balance-xor',
        3: 'broadcast',
        4: '802.3ad',
        5: 'balance-tlb',
        6: 'balance-alb',
    }

    def __init__(self, netplan_root):
        self.devices = {} # Maps ifindex to Networkdev
        self.devices_by_name = {} # Maps interface names to Networkdev
        self.default_v4_gateway = None
        self.default_v6_gateway = None
        self.v4_gateway_dev = None
        self.v6_gateway_dev = None
        self.network_routes = {}
        self.netplan_root = netplan_root
        self.parse_netplan_configs()

    def parse_netplan_configs(self):
        self.config = NetplanConfig()
        configs_by_basename = {}
        paths = glob.glob(os.path.join(self.netplan_root, 'lib/netplan', "*.yaml")) + \
          glob.glob(os.path.join(self.netplan_root, 'etc/netplan', "*.yaml")) + \
          glob.glob(os.path.join(self.netplan_root, 'run/netplan', "*.yaml"))
        for path in paths:
            configs_by_basename[os.path.basename(path)] = path
        for _, path in sorted(configs_by_basename.items()):
            try:
                fp = open(path)
            except OSError:
                log.exception("opening %s failed", path)
            with fp:
                self.config.parse_netplan_config(fp.read())

    def get_menu(self):
        return self.additional_options

    def new_link(self, ifindex, link):
        if link.type in NETDEV_IGNORED_IFACE_TYPES:
            return
        if link.name in NETDEV_IGNORED_IFACE_NAMES:
            return
        if link.is_virtual:
            return
        config = self.config.config_for_device(link)
        log.debug("new_link %s %s with config %s", ifindex, link.name, config)
        self.devices[ifindex] = Networkdev(link, config)
        self.devices_by_name[link.name] = Networkdev(link, config)

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
                return

    def del_link(self, ifindex):
        if ifindex in self.devices:
            dev = self.devices[ifindex]
            del self.devices_by_name[dev.name]
            del self.devices[ifindex]

    def get_all_netdevs(self):
        return [v for k, v in sorted(self.devices_by_name.items())]

    def get_configured_interfaces(self):
        return [dev for dev in self.get_all_netdevs() if dev.configured]

    def get_netdev_by_name(self, name):
        return self.devices_by_name[name]

    def add_bond(self, ifname, interfaces, params=[], subnets=[]):
        # This needs rewriting!
        ''' create a bond action and info dict from parameters '''
        for iface in interfaces:
            self.devices[iface].remove_networks()
            self.devices[iface].dhcp4 = False
            self.devices[iface].dhcp6 = False
            self.devices[iface].switchport = True

        info = {
            "bond": {
                "is_master": True,
                "is_slave": False,
                "mode": params['bond-mode'],
                "slaves": interfaces,
            },
            "bridge": {
                "interfaces": [],
                "is_bridge": False,
                "is_port": False,
                "options": {}
            },
            "hardware": {
                "INTERFACE": ifname,
                'ID_MODEL_FROM_DATABASE': " + ".join(interfaces),
                'attrs': {
                    'address': "00:00:00:00:00:00",
                    'speed': None,
                },
            },
            "ip": {
                "addr": "0.0.0.0",
                "netmask": "0.0.0.0",
                "source": None
            },
            "type": "bond"
        }
        bondinfo = make_network_info(ifname, info)
        bonddev = Networkdev(ifname, 'bond')
        bonddev.configure(probe_info=bondinfo)

        # update slave interface info
        for bondifname in interfaces:
            bondif = self.get_interface(bondifname)
            bondif.info.bond['is_slave'] = True
            log.debug('Marking {} as bond slave'.format(bondifname))

        log.debug("add_bond: {} as netdev({})".format(
                  ifname, bonddev))

        self.devices[ifname] = bonddev
        self.info[ifname] = bondinfo

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
        for dev in self.devices.values():
            if dev.type == 'eth':
                ethernets.update(dev.render())
            if dev.type == 'bond':
                bonds.update(dev.render())
            if dev.type == 'wlan':
                wifis.update(dev.render())
        if any(ethernets):
            config['network']['ethernets'] = ethernets
        if any(bonds):
            config['network']['bonds'] = bonds
        if any(wifis):
            config['network']['wifis'] = wifis

        nw_routes = []
        if self.default_v4_gateway:
            nw_routes.append({ 'to': '0.0.0.0/0', 'via': self.default_v4_gateway })
        if self.default_v6_gateway is not None:
            nw_routes.append({ 'to': '::/0', 'via': self.default_v6_gateway })
        if len(nw_routes) > 0:
            config['network']['routes'] = nw_routes

        return config
