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

import logging
import os
import re
import pyudev

from probert.utils import udev_get_attributes

log = logging.getLogger('probert.storage')


class StorageInfo():
    ''' properties:
        .type = [disk, partition, etc.}
        .name = /dev/sda
        .size = 123012034 (bytes)
        .serial = abcdefghijkl
        .vendor = Innotec
        .model = SolidStateRocketDrive
        .devpath = /devices
        .is_virtual =
        .raw = {raw dictionary}
    '''
    def __init__(self, probe_data):
        [self.name] = probe_data
        self.raw = probe_data.get(self.name)

        self.type = self.raw['DEVTYPE']
        self.size = int(self.raw['attrs']['size'])

    def _get_hwvalues(self, keys):
        for key in keys:
            try:
                return self.raw[key]
            except KeyError:
                log.debug('Failed to get key {} from interface {}'.format(key, self.name))

        return None

    @property
    def vendor(self):
        ''' Some disks don't have ID_VENDOR_* instead the vendor
            is encoded in the model: SanDisk_A223JJ3J3 '''
        v = self._get_hwvalues(['ID_VENDOR_FROM_DATABASE', 'ID_VENDOR', 'ID_VENDOR_ID'])
        if v is None:
            v = self.model
            if v is not None:
                return v.split('_')[0]
        return v

    @property
    def model(self):
        return self._get_hwvalues(['ID_MODEL_FROM_DATABASE', 'ID_MODEL', 'ID_MODEL_ID'])

    @property
    def serial(self):
        return self._get_hwvalues(['ID_SERIAL', 'ID_SERIAL_SHORT'])

    @property
    def devpath(self):
        return self._get_hwvalues(['DEVPATH'])

    @property
    def is_virtual(self):
        return self.devpath.startswith('/devices/virtual/')


class Storage():
    def __init__(self, results={}):
        self.results = results
        self.context = pyudev.Context()

    def get_devices_by_key(self, keyname, value):
        try:
            storage = self.results.get('storage')
            return [device for device in storage.keys()
                    if storage[device][keyname] == value]
        except (KeyError, AttributeError):
            return []

    def get_devices(self):
        try:
            return self.results.get('storage').keys()
        except (KeyError, AttributeError):
            return []

    def get_partitions(self, device):
        ''' /dev/sda '''
        try:
            partitions = self.get_devices_by_key('DEVTYPE', 'partition')
            return [part for part in partitions
                    if part.startswith(device)]
        except (KeyError, AttributeError):
            return []

    def get_disks(self):
        try:
            storage = self.results.get('storage')
            return [disk for disk in self.get_devices_by_key('MAJOR', '8')
                    if storage[disk]['DEVTYPE'] == 'disk']
        except (KeyError, AttributeError):
            return []

    def get_device_size(self, device):
        try:
            hwinfo = self.results.get('storage').get(device)
            return hwinfo.get('attrs').get('size')
        except (KeyError, AttributeError):
            return "0"

    def _get_device_size(self, device, is_partition=False):
        ''' device='/dev/sda' '''
        device_dir = os.path.join('/sys/class/block', os.path.basename(device))
        blockdev_size = os.path.join(device_dir, 'size')
        with open(blockdev_size) as d:
            size = int(d.read().strip())

        logsize_base = device_dir
        if not os.path.exists(os.path.join(device_dir, 'queue')):
            parent_dev = os.path.basename(re.split('[\d+]', device)[0])
            logsize_base = os.path.join('/sys/class/block', parent_dev)

        logical_size = os.path.join(logsize_base, 'queue',
                                    'logical_block_size')
        if os.path.exists(logical_size):
            with open(logical_size) as s:
                size *= int(s.read().strip())

        return size

    def probe(self):
        storage = {}
        for device in self.context.list_devices(subsystem='block'):
            if device['MAJOR'] not in ["1", "7"]:
                attrs = udev_get_attributes(device)
                # update the size attr as it may only be the number
                # of blocks rather than size in bytes.
                attrs['size'] = \
                    str(self._get_device_size(device['DEVNAME']))
                storage[device['DEVNAME']] = dict(device)
                storage[device['DEVNAME']].update({'attrs': attrs})

        self.results = storage
        return storage
