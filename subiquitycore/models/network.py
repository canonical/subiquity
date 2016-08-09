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
from subiquitycore.prober import make_network_info
from subiquitycore.model import BaseModel
from subiquitycore.utils import (read_sys_net,
                                 sys_dev_path)

from .actions import (
    BondAction,
    BridgeAction,
    PhysicalAction,
    RouteAction,
    VlanAction,
)

NETDEV_IGNORED_IFACES = ['lo', 'bridge', 'tun', 'tap', 'dummy']
log = logging.getLogger('subiquitycore.models.network')


class Networkdev():
    def __init__(self, ifname, iftype, probe_info=None):
        self.ifname = ifname
        self.iftype = iftype
        self.action = None
        self.probe_info = probe_info

    def configure(self, action, probe_info=None):
        log.debug('Configuring iface {}'.format(self.ifname))
        log.debug('Action: {}'.format(action.get()))
        log.debug('Info: {}'.format(probe_info))
        self.action = action
        self.probe_info = probe_info
        self.configure_from_info()

    def configure_from_info(self):
        log.debug('configuring netdev from info source')

        ip_info = self.probe_info.ip
        sources = ip_info.get('sources', None)
        for idx in range(len(ip_info.get('af_inet', []))):
            if sources[idx] and sources[idx]['method'].startswith('dhcp'):
                self.action.subnets.extend([{'type': 'dhcp'}])
            elif ip_info['af_inet'][idx]['addr'] is not None:
                # FIXME:
                #  - ipv6
                #  - read/fine default dns and route info
                ip_network = \
                    ipaddress.IPv4Interface("{addr}/{netmask}".format(ip_info['af_inet'][idx]))
                self.action.subnets.extend([{
                    'type': 'static',
                    'address': ip_network.with_prefixlen}])

        log.debug('Post config action: {}'.format(self.action.get()))

    def __repr__(self):
        return "%s: %s" % (self.ifname, self.ip)

    @property
    def is_configured(self):
        return (self.action is not None and
                self.probe_info is not None)

    @property
    def type(self):
        return self.iftype

    @property
    def info(self):
        return self.probe_info

    @property
    def subnets(self):
        if not self.is_configured:
            return []
        return self.action.subnets

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
        ip4_methods = []
        ip4_providers = []

        if self.is_configured:
            log.debug('iface is configured, check action')
            log.debug('subnets: {}'.format(self.subnets))
            using_dhcp = [sn for sn in self.subnets
                          if sn['type'].startswith('dhcp')]
            if len(using_dhcp) > 0:
                log.debug('iface is using dhcp, get details')
                ipinfo = self.probe_info.ip
                probed_ip = [ af_inet.get('addr') for af_inet in ipinfo.get('af_inet') ]
                ip4_methods = [ source.get('method') for source in ipinfo.get('sources') ]
                ip4_providers = [ source.get('provider') for source in ipinfo.get('sources') ]
                if probed_ip:
                    ip4 = probed_ip

            else:  # using static
                log.debug('no dhcp, must be static')
                static_sn = [sn for sn in self.subnets
                             if sn['type'] == 'static']
                if len(static_sn) > 0:
                    log.debug('found a subnet entry, use the first')
                    [static_sn] = static_sn
                    ip4 = [static_sn.get('address')]
                    ip4_methods = ['manual']
                    ip4_providers = [static_sn.get('gateway', 'local config')]
                else:
                    log.debug('no subnet entry')

        log.debug('{} IPv4 info: {},{},{}'.format(self.ifname, ip4, ip4_methods,
                                                  ip4_providers))

        ip_info = { 'ip4': ip4,
                    'ip4_methods': ip4_methods,
                    'ip4_providers': ip4_providers,
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

    def remove_subnets(self):
        log.debug('Removing subnets on iface: {}'.format(self.ifname))
        self.action.subnets = []

    def add_subnet(self, subnet_type, network=None, address=None,
                   gateway=None, nameserver=None, searchpath=None):
        if subnet_type not in ['static', 'dhcp', 'dhcp6']:
            raise ValueError(('Invalid subnet type ') + subnet_type)

        # network = 192.168.9.0/24
        # address = 192.168.9.212
        subnet = {
            'type': subnet_type,
        }

        if subnet_type == 'static':
            ipaddr = valid_ipv4_address(address)
            if ipaddr is False:
                raise ValueError(('Invalid IP address ') + address)

            ipnet = valid_ipv4_network(network)
            if ipnet is False:
                raise ValueError(('Invalid IP network ') + network)

            ip_network = ipaddress.IPv4Interface("{}/{}".format(
                ipaddr.compressed, ipnet.prefixlen))
            subnet.update({'address': ip_network.with_prefixlen})

        if gateway:
            gw = valid_ipv4_address(gateway)
            if gw is False:
                raise ValueError(('Invalid gateway IP ') + gateway)
            subnet.update({'gateway': gw.compressed})

        if nameserver:
            subnet.update({'dns_nameserver': nameserver})

        if searchpath:
            subnet.update({'dns_search': searchpath})

        log.debug('Adding subnet:{}'.format(subnet))
        self.action.subnets.extend([subnet])


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
        ('Network finish',
         'network:finish',
         'network_finish'),
        ('Network configure interface',
         base_signal + ':configure-interface',
         'network_configure_interface'),
        ('Network configure ipv4 interface',
         base_signal + ':configure-ipv4-interface',
         'network_configure_ipv4_interface')
    ]

    additional_options = [
        ('Set default route',
         base_signal + ':set-default-route',
         'set_default_route'),
        ('Bond interfaces',
         base_signal + ':bond-interfaces',
         'bond_interfaces'),
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
        self.info = {}
        self.devices = {}
        self.network_devices = {}
        self.network_routes = {}
        self.default_gateway = None

    def reset(self):
        log.debug('resetting network model')
        self.devices = {}
        self.info = {}
        self.default_gateway = None

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
        self.network_devices = self.prober.get_network_devices()
        self.network_routes = self.prober.get_network_routes()

        for iface in [iface for iface in self.network_devices.keys()
                      if iface not in NETDEV_IGNORED_IFACES]:
            ifinfo = self.prober.get_network_info(iface)
            self.info[iface] = ifinfo

        log.debug('probing network complete!')

    def get_routes(self):
        ''' get collection of currently configured routes '''
        return self.network_routes

    def get_interface(self, iface):
        '''get iface object given iface name '''
        log.debug('get_iface({})'.format(iface))
        if iface not in self.devices:
            ifinfo = self.info[iface]
            netdev = Networkdev(iface, ifinfo.type)
            if netdev.type in ['eth', 'wlan']:
                action = PhysicalAction(name=iface,
                                        mac_address=ifinfo.hwaddr)
            elif netdev.type in ['bond']:
                action = BondAction(name=iface,
                                    bond_interfaces=ifinfo.bond['slaves'])
            elif netdev.type in ['bridge']:
                action = \
                    BridgeAction(name=iface,
                                 bridge_interfaces=ifinfo.bridge['interfaces'])
            elif netdev.type in ['vlan']:
                action = VlanAction(name=iface,
                                    vlan_id=ifinfo.vlan.vlan_id)
            else:
                err = ('Unkown netdevice type: ') + netdev.type
                log.error(err)

            try:
                netdev.configure(action, probe_info=ifinfo)
            except Exception as e:
                log.error(e)
            self.devices[iface] = netdev

        return self.devices[iface]

    def get_all_interfaces(self):
        possible_devices = list(set(list(self.devices.keys()) +
                                    list(self.info.keys())))
        possible_ifaces = [self.get_interface(i) for i in
                           sorted(possible_devices) if
                           self.info[i].type not in NETDEV_IGNORED_IFACES]

        log.debug('get_all_interfaces -> {}'.format(",".join(
                                                    [i.ifname for i in
                                                     possible_ifaces])))
        return possible_ifaces

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
            brinfo = self.network_devices[bridge].get('bridge', {})
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
        return [iface for iface in self.network_devices.keys()
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
        if self.default_gateway:
            action = {
                'type': 'route',
                'gateway': self.default_gateway
            }
            return [RouteAction(**action).get()]
        return []

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
        action = BondAction(name=ifname,
                            bond_interfaces=interfaces,
                            params=params)
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
        bonddev.configure(action, probe_info=bondinfo)

        # update slave interface info
        for bondifname in interfaces:
            bondif = self.get_interface(bondifname)
            bondif.info.bond['is_slave'] = True
            log.debug('Marking {} as bond slave'.format(bondifname))

        log.debug("add_bond: {} as netdev({})".format(
                  ifname, bonddev))

        self.devices[ifname] = bonddev
        self.info[ifname] = bondinfo

    def set_default_gateway(self, gateway_input):
        addr = valid_ipv4_address(gateway_input)
        if addr is False:
            raise ValueError(('Invalid gateway IP ') + gateway_input)

        self.default_gateway = addr.compressed
