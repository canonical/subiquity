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

""" Filesystem Model

Provides storage device selection and additional storage
configuration.

"""
import logging
import json
import argparse

from subiquity import models
from subiquity.models.blockdev import Blockdev
from probert import prober
from probert.storage import StorageInfo
log = logging.getLogger('subiquity.filesystemModel')


class FilesystemModel(models.Model):
    """ Model representing storage options
    """

    fs_menu = [
        'Connect iSCSI network disk',
        'Connect Ceph network disk',
        'Create volume group (LVM2)',
        'Create software RAID (MD)',
        'Setup hierarchichal storage (bcache)'
    ]

    partition_menu = [
        'Add first GPT partition',
        'Format or create swap on entire device (unusual, advanced)'
    ]

    supported_filesystems = [
        'ext4',
        'xfs',
        'btrfs',
        'swap',
        'bcache cache',
        'bcache store',
        'leave unformatted'
    ]

    def __init__(self):
        self.storage = {}
        self.info = {}
        self.devices = {}
        self.options = argparse.Namespace(probe_storage=True,
                                          probe_network=False)
        self.prober = prober.Prober(self.options)
        self.probe_storage()

    def probe_storage(self):
        self.prober.probe()
        self.storage = self.prober.get_results().get('storage')
        log.debug('storage probe data:\n{}'.format(
                  json.dumps(self.storage, indent=4, sort_keys=True)))

        # TODO: replace this with Storage.get_device_by_match()
        # which takes a lambda fn for matching
        VALID_MAJORS = ['8', '253']
        for disk in self.storage.keys():
            if self.storage[disk]['DEVTYPE'] == 'disk' and \
               self.storage[disk]['MAJOR'] in VALID_MAJORS:
                log.debug('disk={}\n{}'.format(disk,
                          json.dumps(self.storage[disk], indent=4,
                                     sort_keys=True)))
                self.info[disk] = StorageInfo({disk: self.storage[disk]})

    def get_disk(self, disk):
        if disk not in self.devices:
                self.devices[disk] = Blockdev(disk, self.info[disk].serial)
        return self.devices[disk]

    def get_partitions(self):
        partitions = []
        for dev in self.devices.values():
            partnames = [part.path for part in dev.disk.partitions]
            partitions += partnames

        sorted(partitions)
        return partitions

    def get_available_disks(self):
        return sorted(self.info.keys())

    def get_used_disks(self):
        return [dev.disk.path for dev in self.devices.values()
                if dev.available is False]

    def get_disk_info(self, disk):
        return self.info[disk]

    def get_disk_action(self, disk):
        return self.devices[disk].get_actions()

    def get_actions(self):
        actions = []
        for dev in self.devices.values():
            actions += dev.get_actions()
        return actions
