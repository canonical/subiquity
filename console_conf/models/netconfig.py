# Copyright 2016 Canonical, Ltd.
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

import ipaddress

from probert.network import Network, NetworkInfo

IGNORED_DEVICE_TYPES = ['lo', 'tun', 'tap']

class Device:
    # In general, an element of config['ethernets'] (or
    # config['wifis']) matches an arbitrary set of interfaces. In
    # subiquity, though, it just matches a single interface by
    # name.
    def __init__(self, name, vendor):
        self.name = name
        self.vendor = vendor
        self.dhcp4 = False
        self.dhcp6 = False
        self.addresses = []

    @classmethod
    def from_probe_data(cls, network, info):
        device = cls(info.name, info.vendor)
        hasipv4, hasipv6 = False, False
        ip = network.get_ips(info.name)
        if ip is not None:
            addr = ip['addr']
            mask = ip['netmask']
            address = ipaddress.ip_interface(addr + '/' + mask)
            if address.version == 4:
                hasipv4 = True
            if address.version == 6:
                hasipv6 = True
            device.addresses.append(address)
        if hasipv4:
            device.dhcp4 = True
        if hasipv6:
            device.dhcp6 = True
        return device

    def render(self):
        addresses = []
        for address in self.addresses:
            if address.version == 4 and not self.dhcp4:
                addresses.append(addresses.with_prefixlen)
            if address.version == 6 and not self.dhcp6:
                addresses.append(addresses.with_prefixlen)
        data = {
            'dhcp4': str(self.dhcp4).lower(),
            'dhcp4': str(self.dhcp4).lower(),
            }
        if addresses:
            data['addresses'] = addresses
        return data

class PhysicalDevice(Device):
    pass

class EthernetDevice(PhysicalDevice):
    pass

## class WifiDevice(PhysicalDevice):
##     ## lots of things go here

## class BridgeDevice(Device):
##     def __init__(self, name):
##         Device.__init__(name)
##         self.interfaces = []

class NetworkConfig:
    def __init__(self):
        self.ethernets = {}
        ## self.wifis = {}
        ## self.bridges = {}

    def render(self):
        ethernets = {}
        for ethernet in self.ethernets.values():
            ethernets[ethernet.name] = ethernet.render()
        data = {
            'version': 2,
            }
        if ethernets:
            data['ethernets'] = ethernets
        return {'network': data}

    @classmethod
    def from_probe_data(cls, results):
        config = cls()
        network = Network(results)
        for name, data in network.results['network'].items():
            type = data['type']
            if type in IGNORED_DEVICE_TYPES:
                continue
            if data['bridge']['is_bridge']:
                pass ## bridges not yet supported
            elif data['bond']['is_master']:
                pass ## bridges not yet supported
            if type == 'eth':
                info = NetworkInfo({name:data})
                config.ethernets[name] = EthernetDevice.from_probe_data(network, info)
        return config

if __name__ == "__main__":
    import sys, json, yaml
    data = json.load(open(sys.argv[1]))
    config = NetworkConfig.from_probe_data(data)
    print(yaml.dump(config.render()))
