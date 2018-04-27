import testtools
import json

from probert.storage import Storage, StorageInfo
from probert.tests.fakes import FAKE_PROBE_ALL_JSON


class ProbertTestStorage(testtools.TestCase):
    def setUp(self):
        super(ProbertTestStorage, self).setUp()
        self.results = json.load(open(FAKE_PROBE_ALL_JSON))
        self.storage = Storage(results=self.results)

    def test_storage_init(self):
        self.assertNotEqual(None, self.storage)

    def test_storage_get_devices(self):
        storage_keys = self.results.get('storage').keys()
        self.assertEqual(sorted(self.storage.get_devices()),
                         sorted(storage_keys))

    def test_storage_get_devices_no_storage(self):
        s = Storage()
        self.assertEqual([], s.get_devices())

    def test_storage_get_devices_by_key(self):
        key = 'DEVTYPE'
        val = 'partition'
        plist_1 = self.storage.get_devices_by_key(key, val)
        plist_2 = [p for p in self.results['storage'].keys()
                   if self.results['storage'][p][key] == val]
        self.assertEqual(sorted(plist_1), sorted(plist_2))

    def test_storage_get_devices_by_key_invalid_key(self):
        key = 'lactobacillus'
        val = 'sourbeer'
        plist_1 = self.storage.get_devices_by_key(key, val)
        plist_2 = []
        self.assertEqual(sorted(plist_1), sorted(plist_2))

    def test_storage_get_devices_by_key_invalid_value(self):
        key = 'DEVTYPE'
        val = 'supercomputer'
        plist_1 = self.storage.get_devices_by_key(key, val)
        plist_2 = []
        self.assertEqual(sorted(plist_1), sorted(plist_2))

    def test_storage_get_partitions(self):
        device = '/dev/sda'
        plist_1 = self.storage.get_partitions(device)
        plist_2 = [p for p in 
                   self.storage.get_devices_by_key('DEVTYPE', 'partition')
                   if p.startswith(device)]
        self.assertEqual(sorted(plist_1), sorted(plist_2))

    def test_storage_get_partitions_no_parts(self):
        results = {'storage': {'/dev/sda': { 'DEVTYPE': 'disk', 'MAJOR': '8'}}}
        s = Storage(results=results)
        device = '/dev/sda'
        self.assertEqual([], s.get_partitions(device))

    def test_storage_get_disk_no_disk(self):
        s = Storage()
        self.assertEqual([], s.get_disks())

    def test_storage_get_disks(self):
        disks = [d for d in self.results['storage'].keys()
                 if self.results['storage'][d]['MAJOR'] == '8' and
                    self.results['storage'][d]['DEVTYPE'] == 'disk']
        self.assertEqual(sorted(self.storage.get_disks()),
                         sorted(disks))

    def test_storage_get_device_size(self):
        disk = self.storage.get_disks().pop()
        size = self.results['storage'][disk]['attrs']['size']
        self.assertEqual(self.storage.get_device_size(disk), size)

    #TODO:
    # def test_storage_probe()


class ProbertTestStorageInfo(testtools.TestCase):
    ''' properties:
        .name = /dev/sda
        .type = disk
        .vendor = SanDisk
        .model = SanDisk_12123123
        .serial = aaccasdf
        .devpath = /devices
        .is_virtual =
        .raw = {raw dictionary}
    '''
    def setUp(self):
        super(ProbertTestStorageInfo, self).setUp()
        self.results = json.load(open(FAKE_PROBE_ALL_JSON))

    def test_storageinfo_init(self):
        probe_data = {
            '/dev/sda': {
                'DEVTYPE': 'disk',
                'attrs': {
                    'size': '1000000'
                }
            }
        }
        si = StorageInfo(probe_data)
        self.assertNotEqual(si, None)

    def test_storageinfo_attributes(self):
        sda = {'/dev/sda': self.results.get('storage').get('/dev/sda')}
        si = StorageInfo(probe_data=sda)
        props = {
            'name': '/dev/sda',
            'type': 'disk',
            'vendor': 'SanDisk',
            'model': 'SanDisk_SD5SG2128G1052E',
            'serial': 'SanDisk_SD5SG2128G1052E_133507400177',
            'devpath': '/devices/pci0000:00/0000:00:1f.2/ata1/host0/target0:0:0/0:0:0:0/block/sda',
            'is_virtual': False,
            'raw': sda.get('/dev/sda')
        }
        for (prop, value) in props.items():
            self.assertEqual(getattr(si, prop), value)
