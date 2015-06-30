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
import math
from probert import prober


class FilesystemModel(models.Model):
    """ Model representing storage options
    """

    additional_options = ['Connecti iSCSI network disk',
                          'Connect Ceph network disk',
                          'Create volume group (LVM2)',
                          'Create software RAID (MD)',
                          'Setup hierarchichal storage (bcache)']

    def __init__(self):
        self.storage = {}
        self.options = argparse.Namespace(probe_storage=True,
                                          probe_network=False)
        self.prober = prober.Prober(self.options)

    def probe_storage(self):
        self.prober.probe()
        self.storage = self.prober.get_results().get('storage')

    def get_available_disks(self):
        return [disk for disk in self.storage.keys()
                if self.storage[disk]['DEVTYPE'] == 'disk' and
                self.storage[disk]['MAJOR'] == '8']

    def get_partitions(self):
        return [part for part in self.storage.keys()
                if self.storage[part]['DEVTYPE'] == 'partition' and
                self.storage[part]['MAJOR'] == '8']

    def _humanize_size(self, size):
        size = abs(size)
        if size == 0:
            return "0B"
        units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
        p = math.floor(math.log(size, 2) / 10)
        return "%.3f %s" % (size / math.pow(1024, p), units[int(p)])

    def get_disk_size(self, disk):
        return self._humanize_size(
            int(self.storage[disk]['attrs']['size']) * 512)
