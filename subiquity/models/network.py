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
from subiquity.model import ModelPolicy
from subiquity.utils import (read_sys_net,
                             sys_dev_path)

from .actions import (
    BondAction,
    BridgeAction,
    PhysicalAction,
    RouteAction,
    VlanAction,
)

NETDEV_IGNORED_IFACES = ['lo', 'bridge', 'tun', 'tap']
log = logging.getLogger('subiquity.models.network')


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
        source = ip_info.get('source', None)
        if source and source['method'].startswith('dhcp'):
            self.action.subnets.extend([{'type': 'dhcp'}])
        elif ip_info['addr'] is not None:
            # FIXME:
            #  - ipv6
            #  - read/fine default dns and route info
            ip_network = \
                ipaddress.IPv4Interface("{addr}/{netmask}".format(**ip_info))
            self.action.subnets.extend([{
                'type': 'static',
                'address': ip_network.with_prefixlen}])

        log.debug('Post config action: {}'.format(self.action.get()))

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
        ip = 'No IPv4 configuration'
        ip_method = None
        ip_provider = None

        if self.is_configured:
            log.debug('iface is configured, check action')
            log.debug('subnets: {}'.format(self.subnets))
            using_dhcp = [sn for sn in self.subnets
                          if sn['type'].startswith('dhcp')]
            if len(using_dhcp) > 0:
                log.debug('iface is using dhcp, get details')
                ipinfo = self.probe_info.ip
                probed_ip = ipinfo.get('addr')
                ip_method = ipinfo.get('source').get('method')
                ip_provider = ipinfo.get('source').get('provider')
                if probed_ip:
                    ip = probed_ip

            else:  # using static
                log.debug('no dhcp, must be static')
                static_sn = [sn for sn in self.subnets
                             if sn['type'] == 'static']
                if len(static_sn) > 0:
                    log.debug('found a subnet entry, use the first')
                    [static_sn] = static_sn
                    ip = static_sn.get('address')
                    ip_method = 'manual'
                    ip_provider = 'local config'
                else:
                    log.debug('no subnet entry')

        log.debug('{} ipinfo: {},{},{}'.format(self.ifname, ip, ip_method,
                                               ip_provider))
        return (ip, ip_method, ip_provider)

    @property
    def ip(self):
        ip, *_ = self._get_ip_info()
        return ip

    @property
    def ip_method(self):
        _, ip_method, _ = self._get_ip_info()
        return ip_method

    @property
    def ip_provider(self):
        _, _, ip_provider = self._get_ip_info()
        return ip_provider

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


class NetworkModel(ModelPolicy):
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
        # ('Bond interfaces',
        #  'network:bond-interfaces',
        #  'bond_interfaces'),
        # ('Install network driver',
        #  'network:install-network-driver',
        #  'install_network_driver')
    ]

    def __init__(self, prober, opts):
        self.opts = opts
        self.prober = prober
        self.info = {}
        self.devices = {}
        self.network = {}
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
        self.network = self.prober.get_network()

        for iface in [iface for iface in self.network.keys()
                      if iface not in NETDEV_IGNORED_IFACES]:
            ifinfo = self.prober.get_network_info(iface)
            self.info[iface] = ifinfo

        log.debug('probing network complete!')

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

            netdev.configure(action, probe_info=ifinfo)
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
            brinfo = self.network[bridge].get('bridge', {})
            if brinfo:
                if iface in brinfo['interfaces']:
                    return True

        return False

    def iface_get_speed(self, iface):
        '''string'ify and bucketize iface speed:
           1M, 10M, 1G, 10G, 40G, 100G
        '''
        hwattr = self.devices[iface].info.hwinfo['attrs']
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
        return [iface for iface in self.network.keys()
                if self.iface_is_bridge(iface)]

    def get_vendor(self, iface):
        hwinfo = self.devices[iface].info.hwinfo
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
        hwinfo = self.devices[iface].info.hwinfo
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
        bondinfo = self.devices[iface].info.bond
        if bondinfo:
            if bondinfo['is_master'] is True or bondinfo['is_slave'] is True:
                return True
        return False

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
            'speed': self.iface_get_speed(iface),
            'vendor': self.get_vendor(iface),
            'model': self.get_model(iface),
            'ip': self.devices[iface].ip,
        }
        return info

    # update or change devices
    def add_bond(self, ifname, interfaces, params=[], subnets=[]):
        ''' take bondname and then a set of options '''
        action = {
            'type': 'bond',
            'name': ifname,
            'bond_interfaces': interfaces,
            'params': params,
            'subnets': subnets,
        }
        self.configured_interfaces.update({ifname: BondAction(**action)})
        log.debug("add_bond: {} as BondAction({})".format(
                  ifname, action))

    def set_default_gateway(self, gateway_input):
        addr = valid_ipv4_address(gateway_input)
        if addr is False:
            raise ValueError(('Invalid gateway IP ') + gateway_input)

        self.default_gateway = addr.compressed
