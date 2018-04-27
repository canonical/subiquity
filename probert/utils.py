from copy import deepcopy
import glob
import itertools
import os
import re

import pyudev

NET_CONFIG_OPTIONS = [
    "address", "netmask", "broadcast", "network", "metric", "gateway",
    "pointtopoint", "media", "mtu", "hostname", "leasehours", "leasetime",
    "vendor", "client", "bootfile", "server", "hwaddr", "provider", "frame",
    "netnum", "endpoint", "local", "ttl",
]

NET_CONFIG_COMMANDS = [
    "pre-up", "up", "post-up", "down", "pre-down", "post-down",
]

NET_CONFIG_BRIDGE_OPTIONS = [
    "bridge_ageing", "bridge_bridgeprio", "bridge_fd", "bridge_gcinit",
    "bridge_hello", "bridge_maxage", "bridge_maxwait", "bridge_stp",
]


# from juju-deployer utils.relation_merge
def dict_merge(onto, source):
    target = deepcopy(onto)
    # Support list of relations targets
    if isinstance(onto, list) and isinstance(source, list):
        target.extend(source)
        return target
    for (key, value) in source.items():
        if key in target:
            if isinstance(target[key], dict) and isinstance(value, dict):
                target[key] = dict_merge(target[key], value)
            elif isinstance(target[key], list) and isinstance(value, list):
                target[key] = list(set(target[key] + value))
        else:
            target[key] = value
    return target


if pyudev.__version_info__ < (0, 18):
    def udev_get_attributes(device):
        r = {}
        for key in device.attributes:
            val = device.attributes.get(key)
            if isinstance(val, bytes):
                val = val.decode('utf-8', 'replace')
            r[key] = val
        return r
else:
    def udev_get_attributes(device):
        r = {}
        for key in device.attributes.available_attributes:
            val = device.attributes.get(key)
            if isinstance(val, bytes):
                val = val.decode('utf-8', 'replace')
            r[key] = val
        return r


# split lists into N lists by predicate
def partitionn2(items, predicate=int, n=2):
    return ((lambda i, tee: (item for pred, item in tee if pred == i))(x, t)
            for x, t in enumerate(itertools.tee(((predicate(item), item)
                                  for item in items), n)))


# unpack generators into key, value pair
# where key is first item (list[0]) and
# value is remainder (list[1:])
def partition_to_pair(input):
    """Unpack a partition into a tuple of (first partition, second partition)

    param: partition iterator from partitionn2
    """
    items = input.split()
    partitions = partitionn2(items=items,
                             predicate=lambda x: items.index(x) != 0,
                             n=2)
    data = [list(p) for p in partitions]
    [key], value = data
    return key, value


def disentagle_data_from_whitespace(data):
    # disentagle the data from whitespace
    return [x.split(';')[0].strip() for x in data.split('\n')
            if len(x)]


def dictify_lease(lease):
    """Transform lease string into dictionary of attributes

    params: lease: string if a dhcp lease structure { to }
    """
    lease_dict = {}
    options = {}
    for line in disentagle_data_from_whitespace(lease):
        if len(line) <= 0:
            continue

        key, value = partition_to_pair(line)
        if key == 'option':
            options.update({value[0]: value[1]})
        else:
            value = " ".join(value)
            lease_dict.update({key: value})

    lease_dict.update({'options': options})
    return lease_dict


def parse_dhclient_leases_file(leasedata):
    """Parses dhclient leases file data, returning dictionary of leases

    :param leasesdata: string of lease data read from leases file
    """
    return [dictify_lease(lease) for lease in
            re.findall(r'{([^{}]*)}', leasedata.replace('"', ''))]


def parse_networkd_lease_file(leasedata):
    """Parses systemd/networkd/netif lease data, returns dict"""
    lease = {}
    for line in leasedata.split('\n'):
        if line.startswith('#') or len(line) < 1:
            continue
        keyvalue = line.split('=')
        lease[keyvalue[0].lower()] = keyvalue[1]
    return lease


def get_dhclient_d():
    # find lease files directory
    supported_dirs = ["/var/lib/dhcp", "/var/lib/dhclient"]
    for d in supported_dirs:
        if os.path.exists(d):
            return d
    return None


def parse_etc_network_interfaces(ifaces, contents, path):
    """Parses the file contents, placing result into ifaces.

    :param ifaces: interface dictionary
    :param contents: contents of interfaces file
    :param path: directory interfaces file was located
    """
    currif = None
    src_dir = path
    for line in contents.splitlines():
        line = line.strip()
        if line.startswith('#'):
            continue
        split = line.split(' ')
        option = split[0]
        if option == "source-directory":
            src_dir = os.path.join(path, split[1])
        elif option == "source":
            src_path = os.path.join(src_dir, split[1])
            for src_file in glob.glob(src_path):
                with open(src_file, "r") as fp:
                    src_data = fp.read().strip()
                parse_etc_network_interfaces(
                    ifaces, src_data,
                    os.path.dirname(os.path.abspath(src_file)))
        elif option == "auto":
            for iface in split[1:]:
                if iface not in ifaces:
                    ifaces[iface] = {}
                ifaces[iface]['auto'] = True
        elif option == "iface":
            iface, family, method = split[1:4]
            if iface not in ifaces:
                ifaces[iface] = {}
            elif 'family' in ifaces[iface]:
                raise Exception("Cannot define %s interface again.")
            ifaces[iface]['family'] = family
            ifaces[iface]['method'] = method
            currif = iface
        elif option == "hwaddress":
            ifaces[currif]['hwaddress'] = split[1]
        elif option in NET_CONFIG_OPTIONS:
            ifaces[currif][option] = split[1]
        elif option in NET_CONFIG_COMMANDS:
            if option not in ifaces[currif]:
                ifaces[currif][option] = []
            ifaces[currif][option].append(' '.join(split[1:]))
        elif option.startswith('dns-'):
            if 'dns' not in ifaces[currif]:
                ifaces[currif]['dns'] = {}
            if option == 'dns-search':
                ifaces[currif]['dns']['search'] = []
                for domain in split[1:]:
                    ifaces[currif]['dns']['search'].append(domain)
            elif option == 'dns-nameservers':
                ifaces[currif]['dns']['nameservers'] = []
                for server in split[1:]:
                    ifaces[currif]['dns']['nameservers'].append(server)
        elif option.startswith('bridge_'):
            if 'bridge' not in ifaces[currif]:
                ifaces[currif]['bridge'] = {}
            if option in NET_CONFIG_BRIDGE_OPTIONS:
                bridge_option = option.replace('bridge_', '')
                ifaces[currif]['bridge'][bridge_option] = split[1]
            elif option == "bridge_ports":
                ifaces[currif]['bridge']['ports'] = []
                for iface in split[1:]:
                    ifaces[currif]['bridge']['ports'].append(iface)
            elif option == "bridge_hw" and split[1].lower() == "mac":
                ifaces[currif]['bridge']['mac'] = split[2]
            elif option == "bridge_pathcost":
                if 'pathcost' not in ifaces[currif]['bridge']:
                    ifaces[currif]['bridge']['pathcost'] = {}
                ifaces[currif]['bridge']['pathcost'][split[1]] = split[2]
            elif option == "bridge_portprio":
                if 'portprio' not in ifaces[currif]['bridge']:
                    ifaces[currif]['bridge']['portprio'] = {}
                ifaces[currif]['bridge']['portprio'][split[1]] = split[2]
    for iface in ifaces.keys():
        if 'auto' not in ifaces[iface]:
            ifaces[iface]['auto'] = False
