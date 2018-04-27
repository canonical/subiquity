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

import abc
import ipaddress
import jsonschema
import logging
import os
import socket

import pyudev

from probert import _nl80211, _rtnetlink
from probert.utils import udev_get_attributes

log = logging.getLogger('probert.network')

# Standard interface flags (net/if.h)
IFF_UP = 0x1                   # Interface is up.
IFF_BROADCAST = 0x2            # Broadcast address valid.
IFF_DEBUG = 0x4                # Turn on debugging.
IFF_LOOPBACK = 0x8             # Is a loopback net.
IFF_POINTOPOINT = 0x10         # Interface is point-to-point link.
IFF_NOTRAILERS = 0x20          # Avoid use of trailers.
IFF_RUNNING = 0x40             # Resources allocated.
IFF_NOARP = 0x80               # No address resolution protocol.
IFF_PROMISC = 0x100            # Receive all packets.
IFF_ALLMULTI = 0x200           # Receive all multicast packets.
IFF_MASTER = 0x400             # Master of a load balancer.
IFF_SLAVE = 0x800              # Slave of a load balancer.
IFF_MULTICAST = 0x1000         # Supports multicast.
IFF_PORTSEL = 0x2000           # Can set media type.
IFF_AUTOMEDIA = 0x4000         # Auto media select active.

IFA_F_PERMANENT = 0x80

BOND_MODES = [
    "balance-rr",
    "active-backup",
    "balance-xor",
    "broadcast",
    "802.3ad",
    "balance-tlb",
    "balance-alb",
    ]

# This json schema describes the links as they are serialized onto
# disk by probert --network. It also describes the format of some of
# the attributes of Link instances.
link_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "link",
    "type": "object",
    "additionalProperties": False,
    "required": ["addresses", "udev_data", "netlink_data", "type", "bond", "bridge"],
    "properties": {
        "addresses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "address": {"type": "string"},
                    "ip": {"type": "string"},
                    "family": {"type": "integer"},
                    "source": {"type": "string"},
                    "scope": {"type": "string"},
                    },
                },
            },
        "type": {
            "type": "string",
            #"enum": ["eth", "wlan", "bridge", "vlan"], # there are more
            },
        "bond": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "is_master": {"type": "boolean"},
                "is_slave": {"type": "boolean"},
                "slaves": {
                    "type": "array",
                    "items": {"type": "string"},
                    },
                "mode": {
                    "oneOf": [
                        {"type": "string", "enum": BOND_MODES},
                        {"type": "null"},
                        ],
                    },
                },
            },
        "udev_data": {
            "type": "object",
            "properties": {
                "attrs": {
                    "type": "object",
                    "additionalProperties": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "null"},
                            ],
                        },
                    },
                },
            "additionalProperties": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "null"},
                    ],
                },
            },
        "netlink_data": {
            "type": "object",
            "properties": {
                "ifindex": {"type": "integer"},
                "flags": {"type": "integer"},
                "arptype": {"type": "integer"},
                "family": {"type": "integer"},
                "name": {"type": "string"},
                },
            },
        "bridge": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "is_bridge": {"type": "boolean"},
                "is_port": {"type": "boolean"},
                "interfaces": {"type": "array", "items": {"type": "string"}},
                "options": {  # /sys/class/net/brX/bridge/<options key>
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    },
                },
            },
        "wlan": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "ssid": {"type": ["null", "string"]},
                "visible_ssids": {
                    "type": "array",
                    "items": {"type": "string"},
                    },
                "scan_state": {"type": ["null", "string"]},
                },
            },
        },
    }

def _compute_type(iface, arptype):
    if not iface:
        return '???'

    sysfs_path = os.path.join('/sys/class/net', iface)
    if not os.path.exists(sysfs_path):
        log.debug('No sysfs path to {}'.format(sysfs_path))
        return None

    DEV_TYPE = '???'

    if arptype == 1:
        DEV_TYPE = 'eth'
        if os.path.isdir(os.path.join(sysfs_path, 'wireless')) or \
           os.path.islink(os.path.join(sysfs_path, 'phy80211')):
            DEV_TYPE = 'wlan'
        elif os.path.isdir(os.path.join(sysfs_path, 'bridge')):
            DEV_TYPE = 'bridge'
        elif os.path.isfile(os.path.join('/proc/net/vlan', iface)):
            DEV_TYPE = 'vlan'
        elif os.path.isdir(os.path.join(sysfs_path, 'bonding')):
            DEV_TYPE = 'bond'
        elif os.path.isfile(os.path.join(sysfs_path, 'tun_flags')):
            DEV_TYPE = 'tap'
        elif os.path.isdir(
                os.path.join('/sys/devices/virtual/net', iface)):
            if iface.startswith('dummy'):
                DEV_TYPE = 'dummy'
    elif arptype == 24:  # firewire ;; IEEE 1394 - RFC 2734
        DEV_TYPE = 'eth'
    elif arptype == 32:  # InfiniBand
        if os.path.isdir(os.path.join(sysfs_path, 'bonding')):
            DEV_TYPE = 'bond'
        elif os.path.isdir(os.path.join(sysfs_path, 'create_child')):
            DEV_TYPE = 'ib'
        else:
            DEV_TYPE = 'ibchild'
    elif arptype == 512:
        DEV_TYPE = 'ppp'
    elif arptype == 768:
        DEV_TYPE = 'ipip'      # IPIP tunnel
    elif arptype == 769:
        DEV_TYPE = 'ip6tnl'   # IP6IP6 tunnel
    elif arptype == 772:
        DEV_TYPE = 'lo'
    elif arptype == 776:
        DEV_TYPE = 'sit'      # sit0 device - IPv6-in-IPv4
    elif arptype == 778:
        DEV_TYPE = 'gre'      # GRE over IP
    elif arptype == 783:
        DEV_TYPE = 'irda'     # Linux-IrDA
    elif arptype == 801:
        DEV_TYPE = 'wlan_aux'
    elif arptype == 65534:
        DEV_TYPE = 'tun'

    if iface.startswith('ippp') or iface.startswith('isdn'):
        DEV_TYPE = 'isdn'
    elif iface.startswith('mip6mnha'):
        DEV_TYPE = 'mip6mnha'

    if len(DEV_TYPE) == 0:
        print('Failed to determine interface type for {}'.format(iface))
        return None

    return DEV_TYPE


def _get_bonding(ifname, flags):

    def _iface_is_master():
        return bool(flags & IFF_MASTER) != 0

    def _iface_is_slave():
        return bool(flags & IFF_SLAVE) != 0

    def _get_slave_iface_list():
        try:
            if _iface_is_master():
                bond = open('/sys/class/net/%s/bonding/slaves' % ifname).read()
                return bond.split()
            else:
                return []
        except IOError:
            return []

    def _get_bond_mode():
        try:
            if _iface_is_master():
                bond_mode = \
                    open('/sys/class/net/%s/bonding/mode' % ifname).read()
                return bond_mode.split()
        except IOError:
            return None

    mode = _get_bond_mode()
    if mode:
        mode_name = mode[0]
    else:
        mode_name = None
    return {
        'is_master': _iface_is_master(),
        'is_slave': _iface_is_slave(),
        'slaves': _get_slave_iface_list(),
        'mode': mode_name
    }


def _get_bridging(ifname):

    def _iface_is_bridge():
        bridge_path = os.path.join('/sys/class/net', ifname, 'bridge')
        return os.path.exists(bridge_path)

    def _iface_is_bridge_port():
        bridge_port = os.path.join('/sys/class/net', ifname, 'brport')
        return os.path.exists(bridge_port)

    def _get_bridge_iface_list():
        if _iface_is_bridge():
            bridge_path = os.path.join('/sys/class/net', ifname, 'brif')
            return os.listdir(bridge_path)
        return []

    def _get_bridge_options():
        skip_attrs = set(['flush', 'bridge'])  # needs root access, not useful

        if _iface_is_bridge():
            bridge_path = os.path.join('/sys/class/net', ifname, 'bridge')
        elif _iface_is_bridge_port():
            bridge_path = os.path.join('/sys/class/net', ifname, 'brport')
        else:
            return {}

        options = {}
        for bridge_attr_name in os.listdir(bridge_path):
            if bridge_attr_name in skip_attrs:
                continue
            bridge_attr_file = os.path.join(bridge_path, bridge_attr_name)
            with open(bridge_attr_file) as bridge_attr:
                options[bridge_attr_name] = bridge_attr.read().strip()

        return options

    return {
        'is_bridge': _iface_is_bridge(),
        'is_port': _iface_is_bridge_port(),
        'interfaces': _get_bridge_iface_list(),
        'options': _get_bridge_options(),
    }


def netlink_attr(attr):
    def get(obj):
        return obj.netlink_data[attr]
    return property(get)


def udev_attr(keys, missing):
    def get(obj):
        for k in keys:
            if k in obj.udev_data:
                return obj.udev_data[k]
        return missing
    return property(get)


class Link:

    @classmethod
    def from_probe_data(cls, netlink_data, udev_data):
        # This is a bit of a hack, but sometimes the interface has
        # already been renamed by udev by the time we get here, so we
        # can't use netlink_data['name'] to go poking about in
        # /sys/class/net.
        name = socket.if_indextoname(netlink_data['ifindex'])
        return cls(
            addresses={},
            type=_compute_type(name, netlink_data['arptype']),
            udev_data=udev_data,
            netlink_data=netlink_data,
            bond=_get_bonding(name, netlink_data['flags']),
            bridge=_get_bridging(name))

    @classmethod
    def from_saved_data(cls, link_data):
        address_objs = {}
        for addr in link_data['addresses']:
            a = Address.from_saved_data(addr)
            address_objs[str(a.ip)] = a
        link_data['addresses'] = address_objs
        return cls(**link_data)

    def __init__(self, addresses, type, udev_data, netlink_data, bond, bridge, wlan=None):
        self.addresses = addresses
        self.type = type
        self.udev_data = udev_data
        self.netlink_data = netlink_data
        self.bond = bond
        self.bridge = bridge
        self.wlan = wlan

    def mark_as_wlan(self):
        if self.wlan is None:
            self.wlan = {
                'visible_ssids': [],
                'ssid': None,
                'scan_state': None,
            }

    def serialize(self):
        r = {
            "addresses": [a.serialize() for a in self.addresses.values()],
            "udev_data": self.udev_data,
            "type": self.type,
            "netlink_data": self.netlink_data,
            "bond": self.bond,
            "bridge": self.bridge,
            }
        if self.wlan is not None:
            r["wlan"] = self.wlan
        jsonschema.validate(r, link_schema)
        return r

    flags = netlink_attr("flags")
    ifindex = netlink_attr("ifindex")
    name = netlink_attr("name")
    hwaddr = property(lambda self:self.udev_data['attrs']['address'])

    vendor = udev_attr(['ID_VENDOR_FROM_DATABASE', 'ID_VENDOR', 'ID_VENDOR_ID'], "Unknown Vendor")
    model = udev_attr(['ID_MODEL_FROM_DATABASE', 'ID_MODEL', 'ID_MODEL_ID'], "Unknown Model")
    driver = udev_attr(['ID_NET_DRIVER', 'ID_USB_DRIVER'], "Unknown Driver")
    devpath = udev_attr(['DEVPATH'], "Unknown devpath")

    hwaddr = property(lambda self:self.udev_data['attrs']['address'])

    # This is the logic ip from iproute2 uses to determine whether
    # to show NO-CARRIER or not. It only really makes sense for a
    # wired connection.
    is_connected = property(lambda self:(not (self.flags & IFF_UP)) or (self.flags & IFF_RUNNING))
    is_virtual = property(lambda self:self.devpath.startswith('/devices/virtual/'))

    @property
    def ssid(self):
        if self.wlan:
            return self.wlan['ssid']
        else:
            return None


_scope_str = {
    0: 'global',
	200: "site",
	253: "link",
	254: "host",
	255: "nowhere",
}


class Address:

    def __init__(self, address, family, source, scope):
        self.address = ipaddress.ip_interface(address)
        self.ip = self.address.ip
        self.family = family
        self.source = source
        self.scope = scope

    def serialize(self):
        return {
            'source': self.source,
            'family': self.family,
            'address': str(self.address),
            'scope': self.scope,
            }

    @classmethod
    def from_probe_data(cls, netlink_data):
        address = netlink_data['local'].decode('latin-1')
        family = netlink_data['family']
        if netlink_data.get('flags', 0) & IFA_F_PERMANENT:
            source = 'static'
        else:
            source = 'dhcp'
        scope = netlink_data['scope']
        scope = str(_scope_str.get(scope, scope))
        return cls(address, family, source, scope)

    @classmethod
    def from_saved_data(cls, link_data):
        return Address(**link_data)


class NetworkObserver(abc.ABC):
    """A NetworkObserver observes the network state.

    It calls methods on a NetworkEventReceiver in response to changes.
    """

    @abc.abstractmethod
    def start(self):
        pass

    @abc.abstractmethod
    def data_ready(self, fd):
        pass


class NetworkEventReceiver(abc.ABC):
    """NetworkEventReceiver has methods called on it in response to network chagnes."""

    @abc.abstractmethod
    def new_link(self, ifindex, link):
        pass

    @abc.abstractmethod
    def update_link(self, ifindex):
        pass

    @abc.abstractmethod
    def del_link(self, ifindex):
        pass

    @abc.abstractmethod
    def route_change(self, action, data):
        pass


class TrivialEventReceiver(NetworkEventReceiver):

    def new_link(self, ifindex, link):
        pass

    def update_link(self, ifindex):
        pass

    def del_link(self, ifindex):
        pass

    def route_change(self, action, data):
        pass


class UdevObserver(NetworkObserver):
    """Use udev/netlink to observe network changes."""

    def __init__(self, receiver=None):
        self._links = {}
        self.context = pyudev.Context()
        if receiver is None:
            receiver = TrivialEventReceiver()
        assert isinstance(receiver, NetworkEventReceiver)
        self.receiver = receiver

    def start(self):
        self.rtlistener = _rtnetlink.listener(self)
        self.rtlistener.start()

        self._fdmap =  {
            self.rtlistener.fileno(): self.rtlistener.data_ready,
            }

        try:
            self.wlan_listener = _nl80211.listener(self)
            self.wlan_listener.start()
            self._fdmap.update({
                self.wlan_listener.fileno(): self.wlan_listener.data_ready,
                })
        except RuntimeError:
            log.debug('could not start wlan_listener')

        return list(self._fdmap)

    def data_ready(self, fd):
        self._fdmap[fd]()

    def link_change(self, action, data):
        log.debug('link_change %s %s', action, data)
        for k, v in data.items():
            if isinstance(v, bytes):
                data[k] = v.decode('utf-8', 'replace')
        ifindex = data['ifindex']
        if action == 'DEL':
            if ifindex in self._links:
                del self._links[ifindex]
                self.receiver.del_link(ifindex)
            return
        if action == 'CHANGE':
            if ifindex in self._links:
                dev = self._links[ifindex]
                # Trigger a scan when a wlan device goes up
                # Not sure if this is required as devices seem to scan as soon
                # as they go up? (in which case this fails with EBUSY, so it's
                # just spam in the logs).
                if dev.type == 'wlan' and (not (dev.flags & IFF_UP)) and (data['flags'] & IFF_UP):
                    try:
                        self.trigger_scan(ifindex)
                    except RuntimeError:
                        log.exception('on-up trigger_scan failed')
                dev.netlink_data = data
                # If a device appears and is immediately renamed, the
                # initial _compute_type can fail to find the sysfs
                # directory. Have another go now.
                if dev.type is None:
                    dev.type = _compute_type(dev.name)
            self.receiver.update_link(ifindex)
            return
        udev_devices = list(self.context.list_devices(IFINDEX=str(ifindex)))
        if len(udev_devices) == 0:
            # Has disappeared already?
            return
        udev_device = udev_devices[0]
        udev_data = dict(udev_device)
        udev_data['attrs'] = udev_get_attributes(udev_device)
        link = Link.from_probe_data(data, udev_data)
        self._links[ifindex] = link
        self.receiver.new_link(ifindex, link)

    def addr_change(self, action, data):
        log.debug('addr_change %s %s', action, data)
        link = self._links.get(data['ifindex'])
        if link is None:
            return
        ip = data['local'].decode('latin-1')
        if action == 'DEL':
            link.addresses.pop(ip, None)
            return
        link.addresses[ip] = Address.from_probe_data(data)

    def route_change(self, action, data):
        log.debug('route_change %s %s', action, data)
        for k, v in data.items():
            if isinstance(v, bytes):
                data[k] = v.decode('utf-8', 'replace')
        self.receiver.route_change(action, data)

    def trigger_scan(self, ifindex):
        self.wlan_listener.trigger_scan(ifindex)

    def wlan_event(self, arg):
        log.debug('wlan_event %s', arg)
        ifindex = arg['ifindex']
        if ifindex < 0 or ifindex not in self._links:
            return
        link = self._links[ifindex]
        link.mark_as_wlan()
        if arg['cmd'] == 'TRIGGER_SCAN':
            link.wlan['scan_state'] = 'scanning'
        if arg['cmd'] == 'NEW_SCAN_RESULTS' and 'ssids' in arg:
            ssids = set()
            for (ssid, status) in arg['ssids']:
                ssid = ssid.decode('utf-8', 'replace')
                ssids.add(ssid)
                if status != "no status":
                    link.wlan['ssid'] = ssid
            link.wlan['visible_ssids'] = sorted(ssids)
            link.wlan['scan_state'] = None
        if arg['cmd'] == 'NEW_INTERFACE':
            if link.flags & IFF_UP:
                try:
                    self.trigger_scan(ifindex)
                except RuntimeError: # Can't trigger a scan as non-root, that's OK.
                    log.exception('initial trigger_scan failed')
            else:
                try:
                    self.rtlistener.set_link_flags(ifindex, IFF_UP)
                except RuntimeError:
                    log.exception('set_link_flags failed')
        if arg['cmd'] == 'NEW_INTERFACE' or arg['cmd'] == 'ASSOCIATE':
            if len(arg.get('ssids', [])) > 0:
                link.wlan['ssid'] = arg['ssids'][0][0].decode('utf-8', 'replace')
        if arg['cmd'] == 'DISCONNECT':
            link.wlan['ssid'] = None


class StoredDataObserver:
    """A cheaty observer that just pretends the network is in some pre-arranged state."""

    def __init__(self, saved_data, receiver):
        self.saved_data = saved_data
        for data in self.saved_data['links']:
            jsonschema.validate(data, link_schema)
        self.receiver = receiver

    def start(self):
        for data in self.saved_data['links']:
            link = Link.from_saved_data(data)
            self.receiver.new_link(link.ifindex, link)
        for data in self.saved_data['routes']:
            self.receiver.route_change("NEW", data)
        return []

    def trigger_scan(self, ifindex):
        pass

    def data_ready(self, fd):
        pass


class NetworkProber:

    def probe(self):
        class CollectingReceiver(TrivialEventReceiver):
            def __init__(self):
                self.all_links = set()
                self.route_data = []
            def new_link(self, ifindex, link):
                self.all_links.add(link)
            def route_change(self, action, data):
                self.route_data.append(data)
        collector = CollectingReceiver()
        observer = UdevObserver(collector)
        observer.start()
        results = {
            'links': [],
            'routes': [],
            }
        for link in collector.all_links:
            results['links'].append(link.serialize())
        for route_data in collector.route_data:
            results['routes'].append(route_data)
        return results



if __name__ == '__main__':
    import pprint
    import select
    c = UdevObserver()
    fds = c.start()

    pprint.pprint(c.links)

    poll_ob = select.epoll()
    for fd in fds:
        poll_ob.register(fd, select.EPOLLIN)
    while True:
        events = poll_ob.poll()
        for (fd, e) in events:
            c.data_ready(fd)
        pprint.pprint(c.links)
