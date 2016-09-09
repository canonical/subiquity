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

import errno
import ipaddress
import logging
import os
import netifaces
from subiquitycore.prober import make_network_info
from subiquitycore.model import BaseModel
from subiquitycore.utils import (read_sys_net,
                                 sys_dev_path)

NETDEV_IGNORED_IFACE_NAMES = ['lo']
NETDEV_IGNORED_IFACE_TYPES = ['bridge', 'tun', 'tap', 'dummy', 'sit']
log = logging.getLogger('subiquitycore.models.network')


class Networkdev():
    def __init__(self, ifname, iftype, probe_info=None):
        self.ifname = ifname
        self.iftype = iftype
        self.is_switchport = False
        self.probe_info = probe_info
        self.dhcp4_addresses = []
        self.dhcp6_addresses = []
        self.ipv4_addresses = []
        self.ipv6_addresses = []
        self.dhcp4 = False
        self.dhcp6 = False
        self.search_domains = []
        self.nameservers = []
        self.gateway = None
        self.essid = None
        self.wpa_psk = None

    def configure(self, probe_info=None):
        log.debug('Configuring iface {}'.format(self.ifname))
        log.debug('Info: {}'.format(probe_info.ip))
        self.probe_info = probe_info
        self.configure_from_info()

    def configure_from_info(self):
        log.debug('configuring netdev from info source')

        if self.iftype == 'wlan':
            self.essid = self.probe_info.raw['essid']

        ip_info = self.probe_info.ip

        sources = ip_info.get('sources', None)
        for idx in range(len(ip_info.get(netifaces.AF_INET, []))):
            address = ip_info.get(netifaces.AF_INET)[idx].get('addr', None)
            netmask = ip_info.get(netifaces.AF_INET)[idx].get('netmask', None)
            method = sources.get(netifaces.AF_INET)[idx].get('method', None)
            provider = sources.get(netifaces.AF_INET)[idx].get('provider', None)

            if address is None:
                continue

            ip_network = \
                ipaddress.IPv4Interface("{}/{}".format(address, netmask))

            if method and method.startswith('dhcp'):
                self.dhcp4 = True
                self.dhcp4_addresses.append([ip_network.with_prefixlen, provider, netifaces.AF_INET])
            else:
                self.ipv4_addresses.append(ip_network.with_prefixlen)

        for idx in range(len(ip_info.get(netifaces.AF_INET6, []))):
            address = ip_info.get(netifaces.AF_INET6)[idx].get('addr', None)
            netmask = ip_info.get(netifaces.AF_INET6)[idx].get('netmask', None)
            method = sources.get(netifaces.AF_INET6)[idx].get('method', None)
            provider = sources.get(netifaces.AF_INET6)[idx].get('provider', None)

            if address is None:
                continue

            raw_ip6 = address.split('%')[0]
            if raw_ip6.startswith('fe80:'):
                continue

            # FIXME: parse netmasks like ffff:ffff:ffff:ffff:: to CIDR notation, because ipaddress is evil.
            ip_network = \
                ipaddress.IPv6Interface("{}/64".format(raw_ip6))

            if method and method.startswith('dhcp'):
                self.dhcp6 = True
                self.dhcp6_addresses.append([ip_network.with_prefixlen, provider, netifaces.AF_INET6])
            else:
                self.ipv6_addresses.append(ip_network.with_prefixlen)

    def render(self):
        log.debug("render to YAML")
        result = { self.ifname:
                   { 
                     'addresses': self.ipv4_addresses + self.ipv6_addresses,
                   } 
                 }

        if self.dhcp4:
            result[self.ifname]['dhcp4'] = True
        if self.dhcp6:
            result[self.ifname]['dhcp6'] = True

        if self.iftype == 'bond':
            result[self.ifname]['interfaces'] = self.probe_info.bond['slaves']

        if self.iftype == 'wlan':
            if self.essid is not None:
                aps = result[self.ifname]['access-points'] = {}
                ap = aps[self.essid] = {
                    'mode': 'infrastructure',
                    }
                if self.wpa_psk is not None:
                    ap['password'] = self.wpa_psk

        return result

    @property
    def is_configured(self):
        return not self.is_switchport

    @property
    def type(self):
        return self.iftype

    @property
    def info(self):
        return self.probe_info

    def _get_ip_info(self):
        ''' try to find the configured ip for this device.
            If the interfaces is not configured, then this will be
            unavailable, 'No IPv4 Address configured'.
            Upon configuring, we are by default in 'dhcp' mode and
            the actual IP will be determined by probing the host
            for the DHCP response.
            If the user has enabled manual configuration
              (self.action is not None and subnets contains
               a 'type: static' element) then we can ignore
            probed information, and instead report the configured
            ip from the static element of the subnets attribute.
        '''
        log.debug('getting ip info on {}'.format(self.ifname))
        ip4 = []
        ip6 = []
        ip4_methods = []
        ip6_methods = []
        ip4_providers = []
        ip6_providers = []

        if self.is_configured:
            log.debug('iface is configured')
            ipinfo = self.probe_info.ip
            log.debug('probe ip: {}'.format(ipinfo))
            probed_ip4 = None
            if ipinfo.get(netifaces.AF_INET) is not None:
                probed_ip4 = [ af_inet.get('addr') for af_inet in ipinfo.get(netifaces.AF_INET) ]
            probed_ip6 = None
            if ipinfo.get(netifaces.AF_INET6) is not None:
                probed_ip6 = [ af_inet6.get('addr') for af_inet6 in ipinfo.get(netifaces.AF_INET6) ]
            if probed_ip4:
                ip4 = probed_ip4
            if probed_ip6:
                ip6 = probed_ip6

            if ipinfo.get('sources', None) is not None:
                for source in ipinfo.get('sources').get(netifaces.AF_INET, []):
                    if source is not None:
                        ip4_methods.append(source.get('method'))
                        ip4_providers.append(source.get('provider'))
                for source in ipinfo.get('sources').get(netifaces.AF_INET6, []):
                    if source is not None:
                        ip6_methods.append(source.get('method'))
                        ip6_providers.append(source.get('provider'))

        log.debug('{} IPv4 info: {},{},{}'.format(self.ifname, ip4, ip4_methods,
                                                  ip4_providers))

        ip_info = { 'ip4': ip4, 'ip6': ip6,
                    'ip4_methods': ip4_methods, 'ip6_methods': ip6_methods,
                    'ip4_providers': ip4_providers, 'ip6_providers': ip6_providers,
                  }

        return ip_info

    @property
    def ip4(self):
        ip_info = self._get_ip_info()
        return ip_info['ip4']

    @property
    def ip4_methods(self):
        ip_info = self._get_ip_info()
        return ip_info['ip4_methods']

    @property
    def ip4_providers(self):
        ip_info = self._get_ip_info()
        return ip_info['ip4_providers']

    @property
    def ip6(self):
        ip_info = self._get_ip_info()
        return ip_info['ip6']

    @property
    def ip6_methods(self):
        ip_info = self._get_ip_info()
        return ip_info['ip6_methods']

    @property
    def ip6_providers(self):
        ip_info = self._get_ip_info()
        return ip_info['ip6_providers']

    def remove_networks(self):
        self.remove_ipv4_networks()
        self.remove_ipv6_networks()

    def remove_ipv4_networks(self):
        self.dhcp4 = False
        self.ipv4_addresses.clear()
        self.dhcp4_addresses.clear()

    def remove_ipv6_networks(self):
        self.dhcp6 = False
        self.ipv6_addresses.clear()
        self.dhcp6_addresses.clear()

    def add_network(self, family, network):
        # result = {
        #    'network': self.subnet_input.value,
        #    'address': self.address_input.value,
        #    'gateway': self.gateway_input.value,
        #    'nameserver': self.nameserver_input.value,
        #    'searchpath': self.searchpath_input.value,
        # }
        address = network['address'].split('/')[0]
        address += '/' + network['network'].split('/')[1]
        if family == netifaces.AF_INET:
            self.ipv4_addresses.append(address)
        elif family == netifaces.AF_INET6:
            self.ipv6_addresses.append(address)
        self.gateway = network['gateway']
        self.nameservers.append(network['nameserver'])
        self.search_domains.append(network['searchdomains'])


def valid_ipv4_address(addr):
    try:
        ip = ipaddress.IPv4Address(addr)
    except ipaddress.AddressValueError:
        return False

    return ip


def valid_ipv4_network(subnet):
    try:
        nw = ipaddress.IPv4Network(subnet)
    except (ipaddress.AddressValueError,
            ipaddress.NetmaskValueError):
        return False

    return nw


class NetworkModel(BaseModel):
    """ Model representing network interfaces
    """
    base_signal = 'menu:network:main'
    signals = [
        ('Network main view',
         base_signal,
         'network'),
        ('Network main view',
         base_signal + ':start',
         'start'),
        ('Network finish',
         'network:finish',
         'network_finish'),
        ('Network configure interface',
         base_signal + ':configure-interface',
         'network_configure_interface'),
        ('Network configure ipv4 interface',
         base_signal + ':configure-ipv4-interface',
         'network_configure_ipv4_interface'),
        ('Network configure wlan interface',
         base_signal + ':configure-wlan-interface',
         'network_configure_wlan_interface'),
    ]

    additional_options = [
        ('Set a custom IPv4 default route',
         base_signal + ':set-default-v4-route',
         'set_default_v4_route'),
        ('Set a custom IPv6 default route',
         base_signal + ':set-default-v6-route',
         'set_default_v6_route'),
        #('Bond interfaces',
        # base_signal + ':bond-interfaces',
        # 'bond_interfaces'),
        # ('Install network driver',
        #  'network:install-network-driver',
        #  'install_network_driver')
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

    def __init__(self, prober, opts):
        self.opts = opts
        self.prober = prober
        self.reset()

    def reset(self):
        log.debug('resetting network model')
        self.devices = {}
        self.info = {}
        self.default_v4_gateway = None
        self.default_v6_gateway = None
        self.v4_gateway_dev = None
        self.v6_gateway_dev = None
        self.network_routes = {}

    def get_signal_by_name(self, selection):
        for x, y, z in self.get_signals():
            if x == selection:
                return y

    def get_signals(self):
        return self.signals + self.additional_options

    def get_menu(self):
        return self.additional_options

    # --- Model Methods ----
    def probe_network(self):
        log.debug('model calling prober.get_network()')
        network_devices = self.prober.get_network_devices()
        self.network_routes = self.prober.get_network_routes()

        for iface in network_devices:
            if iface in NETDEV_IGNORED_IFACE_NAMES:
                continue
            ifinfo = self.prober.get_network_info(iface)
            if ifinfo.type in NETDEV_IGNORED_IFACE_TYPES:
                continue
            self.info[iface] = ifinfo
            netdev = Networkdev(iface, ifinfo.type)
            try:
                log.debug('configuring with: {}'.format(ifinfo))
                netdev.configure(probe_info=ifinfo)
            except Exception as e:
                log.error(e)
            self.devices[iface] = netdev

        log.debug('probing network complete!')

    def get_routes(self):
        ''' get collection of currently configured routes '''
        return self.network_routes

    def get_interface(self, iface):
        '''get iface object given iface name '''
        log.debug('get_iface({})'.format(iface))
        return self.devices[iface]

    def get_all_interfaces(self):
        ifaces = [iface for _, iface in sorted(self.devices.items())]

        log.debug('get_all_interfaces -> {}'.format(",".join(
                                                    [i.ifname for i in
                                                     ifaces])))
        return ifaces

    def get_all_interface_names(self):
        return [i.ifname for i in self.get_all_interfaces()]

    def get_configured_interfaces(self):
        return [iface for iface in self.get_all_interfaces()
                if iface.is_configured]

    def iface_is_up(self, iface):
        # don't attempt to read/open files on dry-run
        if self.opts.dry_run:
            return True

        # The linux kernel says to consider devices in 'unknown'
        # operstate as up for the purposes of network configuration. See
        # Documentation/networking/operstates.txt in the kernel source.
        translate = {'up': True, 'unknown': True, 'down': False}
        return read_sys_net(iface, "operstate", enoent=False,
                            keyerror=False, translate=translate)

    def iface_is_wireless(self, iface):
        # don't attempt to read/open files on dry-run
        if self.opts.dry_run:
            return True

        return os.path.exists(sys_dev_path(iface, "wireless"))

    def iface_is_bridge_member(self, iface):
        ''' scan through all of the bridges
            and see if iface is included in a bridge '''
        bridges = self.get_bridges()
        for bridge in bridges:
            brinfo = self.info[bridge].bridge
            if brinfo:
                if iface in brinfo['interfaces']:
                    return True

        return False

    def iface_get_speed(self, iface):
        '''string'ify and bucketize iface speed:
           1M, 10M, 1G, 10G, 40G, 100G
        '''
        hwattr = self.info[iface].hwinfo['attrs']
        speed = hwattr.get('speed', 0)
        if not speed:
            return None

        speed = int(speed)
        if speed < 1000:
            return "{}M".format(speed)

        return "{}G".format(int(speed / 1000))

    def iface_is_connected(self, iface):
        # don't attempt to read/open files on dry-run
        if self.opts.dry_run:
            return True

        # is_connected isn't really as simple as that.  2 is
        # 'physically connected'. 3 is 'not connected'.
        # but a wlan interface will
        # always show 3.
        try:
            iflink = read_sys_net(iface, "iflink", enoent=False)
            if iflink == "2":
                return True
            if not self.iface_is_wireless(iface):
                return False
            log.debug("'%s' is wireless, basing 'connected' on carrier", iface)

            return read_sys_net(iface, "carrier", enoent=False, keyerror=False,
                                translate={'0': False, '1': True})
        except IOError as e:
            if e.errno == errno.EINVAL:
                return False
            raise

    def get_bridges(self):
        return [iface for iface in self.info
                if self.iface_is_bridge(iface)]

    def get_hw_addr(self, iface):
        ifinfo = self.info[iface]
        return ifinfo.hwaddr

    def get_vendor(self, iface):
        hwinfo = self.info[iface].hwinfo
        vendor_keys = [
            'ID_VENDOR_FROM_DATABASE',
            'ID_VENDOR',
            'ID_VENDOR_ID'
        ]
        for key in vendor_keys:
            try:
                return hwinfo[key]
            except KeyError:
                log.warn('Failed to get key '
                         '{} from interface {}'.format(key, iface))
                pass

        return 'Unknown Vendor'

    def get_model(self, iface):
        hwinfo = self.info[iface].hwinfo
        model_keys = [
            'ID_MODEL_FROM_DATABASE',
            'ID_MODEL_ID'
            'ID_MODEL',
        ]
        for key in model_keys:
            try:
                return hwinfo[key]
            except KeyError:
                log.warn('Failed to get key '
                         '{} from interface {}'.format(key, iface))
                pass

        return 'Unknown Model'

    def iface_is_bonded(self, iface):
        log.debug('checking {} is bonded'.format(iface))
        bondinfo = self.info[iface].bond
        log.debug('bondinfo: {}'.format(bondinfo))
        if bondinfo:
            if bondinfo['is_master'] is True or bondinfo['is_slave'] is True:
                return True
        return False

    def iface_is_bond_slave(self, iface):
        bondinfo = self.info[iface].bond
        log.debug('bondinfo: {}'.format(bondinfo))
        if bondinfo:
            if bondinfo['is_slave'] is True:
                return True
        return False

    def get_bond_masters(self):
        bond_masters = []
        for iface in self.get_all_interface_names():
            bondinfo = self.info[iface].bond
            if bondinfo['is_master'] is True:
                bond_masters.append(iface)

        return bond_masters

    def iface_is_bridge(self, iface):
        return self.devices[iface].type == 'bridge'

    def get_default_route(self):
        route = []
        if self.default_v4_gateway:
            route.append(self.default_v4_gateway)
        else:
            route.append(None)
        if self.default_v6_gateway:
            route.append(self.default_v6_gateway)
        else:
            route.append(None)
        return route

    def get_iface_info(self, iface):
        info = {
            'bonded': self.iface_is_bonded(iface),
            'bond_slave': self.iface_is_bond_slave(iface),
            'bond_master': iface in self.get_bond_masters(),
            'speed': self.iface_get_speed(iface),
            'vendor': self.get_vendor(iface),
            'model': self.get_model(iface),
            'ip': self.devices[iface].ip4,
        }
        return info

    # update or change devices
    def add_bond(self, ifname, interfaces, params=[], subnets=[]):
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
        config = { 'network':
                   {
                     'version': 2,
                   }
                 }
        ethernets = {}
        bonds = {}
        wifis = {}
        for iface in self.devices.values():
            if iface.iftype == 'eth':
                ethernets.update(iface.render())
            if iface.iftype == 'bond':
                bonds.update(iface.render())
            if iface.iftype == 'wlan':
                wifis.update(iface.render())
        if any(ethernets):
            config['network']['ethernets'] = ethernets
        if any(bonds):
            config['network']['bonds'] = bonds
        if any(wifis):
            config['network']['wifis'] = wifis

        routes = self.get_default_route()
        nw_routes = []
        if routes[0] is not None:
            nw_routes.append({ 'to': '0.0.0.0/0', 'via': routes[0] })
        if routes[1] is not None:
            nw_routes.append({ 'to': '::/0', 'via': routes[1] })
        if len(nw_routes) > 0:
            config['network']['routes'] = nw_routes

        return config
