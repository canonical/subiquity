import testtools
import json

from probert.network import Network, NetworkInfo
from probert.tests.fakes import FAKE_PROBE_ALL_JSON


class ProbertTestNetwork(testtools.TestCase):
    def setUp(self):
        super(ProbertTestNetwork, self).setUp()
        self.results = json.load(open(FAKE_PROBE_ALL_JSON))
        self.network = Network(results=self.results)

    def test_network_init(self):
        self.assertNotEqual(None, self.network)

    def test_network_get_interfaces(self):
        ifaces = self.results['network'].keys()
        self.assertEqual(sorted(ifaces), sorted(self.network.get_interfaces()))

    def test_network_get_interfaces_no_nics(self):
        ifaces = []
        n = Network()
        self.assertEqual(ifaces, n.get_interfaces())

    def test_network_get_ips(self):
        for iface in self.network.get_interfaces():
            ip = self.results['network'][iface]['ip']
            self.assertEqual(ip, self.network.get_ips(iface))

    def test_network_get_ips_no_ips(self):
        n = Network()
        self.assertEqual([], n.get_ips('noiface'))

    def test_network_get_hwaddr(self):
        for iface in self.network.get_interfaces():
            hwaddr = \
                self.results['network'][iface]['hardware']['attrs']['address']
            self.assertEqual(hwaddr, self.network.get_hwaddr(iface))

    def test_network_get_iface_type(self):
        # TODO: mock out open/read of sysfs
        #       and use _get_iface_type()
        self.assertEqual('eth', self.network.get_iface_type('eth0'))

    # needs mocking of pyudev.Context()
    # and return mock data
    #def test_network_probe(self):

class ProbertTestNetworkInfo(testtools.TestCase):
    ''' properties:
        .name = eth7
        .type = eth
        .vendor = Innotec
        .model = SuperSonicEtherRocket
        .driver = sser
        .devpath = /devices
        .hwaddr = aa:bb:cc:dd:ee:ff
        .addr = 10.2.7.2
        .netmask = 255.255.255.0
        .broadcast = 10.2.7.255
        .addr6 =
        .is_virtual =
        .raw = {raw dictionary}
        .ip = {ip dict}
        .bond = {bond dict}
        .bridge = {bridge_dict}
    '''
    def setUp(self):
        super(ProbertTestNetworkInfo, self).setUp()
        self.results = json.load(open(FAKE_PROBE_ALL_JSON))

    def test_networkinfo_init(self):
        probe_data = {
            'em1': {
                'bond': {
                    'is_slave': False,
                    'is_master': False,
                    'slaves': [],
                    'mode': None,
                },
                "bridge": {
                    "interfaces": [],
                    "is_bridge": False,
                    "is_port": False,
                    "options": {}
                },
                'hardware': {
                    'attrs': {
                        'address': '00:11:22:33:44:55',
                    }
                },
                'type': 'eth',
                'ip' : {},
            }
        }
        ni = NetworkInfo(probe_data)
        self.assertNotEqual(ni, None)

    def test_networkinfo_attributes(self):
        eth0 = {'eth0': self.results.get('network').get('eth0')}
        ni = NetworkInfo(probe_data=eth0)
        props = {
            'name': 'eth0',
            'type': 'eth',
            'vendor': 'ASIX Electronics Corp.',
            'model': 'AX88179',
            'driver': 'ax88179_178a',
            'devpath': '/devices/pci0000:00/0000:00:14.0/usb3/3-2/3-2.1/3-2.1.1/3-2.1.1:1.0/net/eth0',
            'hwaddr': '00:0a:cd:26:45:33',
            'addr': '192.168.11.58',
            'netmask': '255.255.255.0',
            'broadcast': '192.168.11.255',
            'is_virtual': False,
            'raw': eth0.get('eth0'),
            'bond': eth0.get('eth0').get('bond'),
            'bridge': eth0.get('eth0').get('bridge'),
            'ip': eth0.get('eth0').get('ip'),
        }
        for (prop, value) in props.items():
            self.assertEqual(getattr(ni, prop), value)

