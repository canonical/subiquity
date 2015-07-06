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

from subiquity import models
import argparse
from probert import prober
from probert.storage import StorageInfo
import logging
import json

log = logging.getLogger('subiquity.filesystemModel')


class FilesystemModel(models.Model):
    """ Model representing storage options
    """

    additional_options = ['Connect iSCSI network disk',
                          'Connect Ceph network disk',
                          'Create volume group (LVM2)',
                          'Create software RAID (MD)',
                          'Setup hierarchichal storage (bcache)']

    def __init__(self):
        self.storage = {}
        self.options = argparse.Namespace(probe_storage=True,
                                          probe_network=False)
        self.prober = prober.Prober(self.options)
        self.probe_storage()

    def probe_storage(self):
        self.disks = {}
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
                self.disks[disk] = StorageInfo({disk: self.storage[disk]})
                log.debug('disk={}\n{}'.format(disk,
                          json.dumps(self.storage[disk], indent=4,
                                     sort_keys=True)))

    def get_partitions(self):
        return [part for part in self.storage.keys()
                if self.storage[part]['DEVTYPE'] == 'partition' and
                self.storage[part]['MAJOR'] == '8']

    def get_available_disks(self):
        return self.disks.keys()

    def get_disk_info(self, disk):
        return self.disks[disk]
