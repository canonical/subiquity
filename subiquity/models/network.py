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
import json
import os
from subiquity.model import ModelPolicy
from subiquity.utils import (read_sys_net,
                             sys_dev_path)

from .actions import (
    BondAction,
    RouteAction,
    PhysicalAction,
)


log = logging.getLogger('subiquity.models.network')


class SimpleInterface:
    """ A simple interface class to encapsulate network information for
    particular interface
    """
    def __init__(self, attrs):
        self.attrs = attrs
        for i in self.attrs.keys():
            if self.attrs[i] is None:
                setattr(self, i, "Unknown")
            else:
                setattr(self, i, self.attrs[i])


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
        self.network = {}
        self.configured_interfaces = {}
        self.default_gateway = None

    def reset(self):
        log.debug('resetting network model')
        self.configured_interfaces = {}
        self.network = {}

    def get_signal_by_name(self, selection):
        for x, y, z in self.get_signals():
            if x == selection:
                return y

    def get_signals(self):
        return self.signals + self.additional_options

    def get_menu(self):
        return self.additional_options

    def probe_network(self):
        log.debug('model calling prober.get_network()')
        self.network = self.prober.get_network()
        log.debug('network:\n{}'.format(json.dumps(self.network, indent=4)))

    def iface_is_up(self, iface):
        # don't attempt to read/open files on dry-run
        if self.opts.dry_run:
            return True

        # The linux kernel says to consider devices in 'unknown'
        # operstate as up for the purposes of network configuration. See
        # Documentation/networking/operstates.txt in the kernel source.
        translate = {'up': True, 'unknown': True, 'down': False}
        return read_sys_net(iface, "operstate", enoent=False, keyerror=False,
                            translate=translate)

    def iface_is_wireless(self, iface):
        # don't attempt to read/open files on dry-run
        if self.opts.dry_run:
            return True

        return os.path.exists(sys_dev_path(iface, "wireless"))

    def iface_is_bonded(self, iface):
        bondinfo = self.network[iface].get('bond', {})
        if bondinfo:
            if bondinfo['is_master'] is True or bondinfo['is_slave'] is True:
                return True
        return False

    def iface_is_bridge(self, iface):
        return self.network[iface]['type'] == 'bridge'

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

    def iface_get_ip(self, iface):
        ip = 'No IPv4 connection'
        ifinfo, *_ = self.get_iface_info(iface)
        if not ifinfo.addr.lower().startswith('unknown'):
            ip = ifinfo.addr

        return ip

    def iface_get_speed(self, iface):
        hwattr = self.network[iface]['hardware']['attrs']
        speed = hwattr.get('speed', 0)
        log.debug('speed: {}'.format(speed))

        if not speed:
            return None

        speed = int(speed)
        if speed < 1000:
            return "{}M".format(speed)
        else:
            return "{}G".format(int(speed / 1000))

    def iface_get_ip_provider(self, iface):
        source = self.network[iface]['ip'].get('source')
        log.debug('source: {}'.format(source))
        if not source:
            return None

        return source['provider']

    def iface_get_ip_method(self, iface):
        source = self.network[iface]['ip'].get('source')
        log.debug('source: {}'.format(source))
        if not source:
            return None

        return source['method']

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

    def configure_iface(self, ifname):
        iface_info = self.network[ifname]
        log.debug('iface_info of {}:\n{}'.format(ifname, iface_info))
        mac_address = iface_info['hardware']['attrs'].get('address')

        action = {
            'type': 'physical',
            'name': ifname,
            'mac_address': mac_address,
            'subnets': [],
        }
        ip_info = self.network[ifname]['ip']
        log.debug('iface {} ip info:\n{}'.format(ifname, ip_info))
        source = ip_info.get('source', None)
        if source and source['method'] is 'dhcp':
            action['subnets'].extend([{'type': 'dhcp'}])
        elif ip_info['addr'] is not None:
            # FIXME:
            #  - ipv6
            #  - read/fine default dns and route info
            ip_network = \
                ipaddress.IPv4Interface("{addr}/{netmask}".format(**ip_info))
            action['subnets'].extend([{
                'type': 'static',
                'address': ip_network.with_prefixlen}])
        log.debug("Configuring iface: {} as PhysicalAction({})".format(
                  ifname, action))
        self.configured_interfaces.update({ifname: PhysicalAction(**action)})

    def get_interfaces(self):
        if len(self.configured_interfaces) == 0:
            ignored = ['lo', 'bridge', 'tun', 'tap']
            for ifname in self.network.keys():
                if self.network[ifname]['type'] not in ignored and \
                   self.iface_is_up(ifname):
                    self.configure_iface(ifname)

        return self.configured_interfaces

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

    def add_subnet(self, ifname, subnet):
        if ifname not in self.configured_interfaces:
            raise Exception('No such configured interface: {}'.format(ifname))

        action = self.configured_interfaces[ifname]
        if 'subnets' in action:
            action['subnets'].extend([subnet])
        else:
            action['subnets'] = [subnet]

    def get_default_route(self):
        if self.default_gateway:
            action = {
                'type': 'route',
                'gateway': self.default_gateway
            }
            return [RouteAction(**action).get()]
        return []

    def get_bridges(self):
        return [iface for iface in self.network.keys()
                if self.iface_is_bridge(iface)]

    def get_vendor(self, iface):
        hwinfo = self.network[iface]['hardware']
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
        hwinfo = self.network[iface]['hardware']
        model_keys = [
            'ID_MODEL_FROM_DATABASE',
            'ID_MODEL',
            'ID_MODEL_ID'
        ]
        for key in model_keys:
            try:
                return hwinfo[key]
            except KeyError:
                log.warn('Failed to get key '
                         '{} from interface {}'.format(key, iface))
                pass

        return 'Unknown Model'

    def get_iface_info(self, iface):
        ipinfo = SimpleInterface(self.network[iface]['ip'])
        return (ipinfo, self.get_vendor(iface), self.get_model(iface))
