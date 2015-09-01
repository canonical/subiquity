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

import json
import logging

from .blockdev import Blockdev
import math
from subiquity.model import ModelPolicy


HUMAN_UNITS = ['B', 'K', 'M', 'G', 'T', 'P']
log = logging.getLogger('subiquity.models.filesystem')


class FilesystemModel(ModelPolicy):
    """ Model representing storage options
    """
    prev_signal = (
        'Back to network path',
        'network:show',
        'network'
    )

    signals = [
        ('Filesystem view',
         'filesystem:show',
         'filesystem'),
        ('Filesystem finish',
         'filesystem:finish',
         'filesystem_handler'),
        ('Show disk partition view',
         'filesystem:show-disk-partition',
         'disk_partition'),
        ('Finish disk partition',
         'filesystem:finish-disk-partition',
         'disk_partition_handler'),
        ('Add disk partition',
         'filesystem:add-disk-partition',
         'add_disk_partition'),
        ('Finish add disk partition',
         'filesystem:finish-add-disk-partition',
         'add_disk_partition_handler'),
        ('Format or create swap on entire device (unusual, advanced)',
         'filesystem:create-swap-entire-device',
         'create_swap_entire_device')
    ]

    fs_menu = [
        ('Connect iSCSI network disk',
         'filesystem:connect-iscsi-disk',
         'connect_iscsi_disk'),
        ('Connect Ceph network disk',
         'filesystem:connect-ceph-disk',
         'connect_ceph_disk'),
        ('Create volume group (LVM2)',
         'filesystem:create-volume-group',
         'create_volume_group'),
        ('Create software RAID (MD)',
         'filesystem:create-raid',
         'create_raid'),
        ('Setup hierarchichal storage (bcache)',
         'filesystem:setup-bcache',
         'setup_bcache')
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

    def __init__(self, prober):
        self.prober = prober
        self.info = {}
        self.devices = {}
        self.storage = {}

    def reset(self):
        log.debug('FilesystemModel: resetting disks')
        for disk in self.devices.values():
            disk.reset()

    def get_signal_by_name(self, selection):
        for x, y, z in self.get_signals():
            if x == selection:
                return y

    def get_signals(self):
        return self.signals + self.fs_menu

    def get_menu(self):
        return self.fs_menu

    def probe_storage(self):
        log.debug('model.probe_storage: probing storage')
        self.storage = self.prober.get_storage()
        log.debug('got storage:\n{}'.format(self.storage))
        # TODO: Put this into a logging namespace for probert
        #       since its quite a bit of log information.
        # log.debug('storage probe data:\n{}'.format(
        #          json.dumps(self.storage, indent=4, sort_keys=True)))

        # TODO: replace this with Storage.get_device_by_match()
        # which takes a lambda fn for matching
        VALID_MAJORS = ['8', '253']
        for disk in self.storage.keys():
            if self.storage[disk]['DEVTYPE'] == 'disk' and \
               self.storage[disk]['MAJOR'] in VALID_MAJORS:
                log.debug('disk={}\n{}'.format(disk,
                          json.dumps(self.storage[disk], indent=4,
                                     sort_keys=True)))
                self.info[disk] = self.prober.get_storage_info(disk)

    def get_disk(self, disk):
        log.debug('probe_storage: get_disk()')
        if disk not in self.devices:
            self.devices[disk] = Blockdev(disk, self.info[disk].serial,
                                          self.info[disk].model,
                                          size=self.info[disk].size)
        return self.devices[disk]

    def get_partitions(self):
        log.debug('probe_storage: get_partitions()')
        partitions = []
        for dev in self.devices.values():
            partnames = [part.path for (num, part) in
                         dev.disk.partitions.items()]
            partitions += partnames

        sorted(partitions)
        log.debug('probe_storage: get_partitions() returns: {}'.format(
                  partitions))
        return partitions

    def get_available_disks(self):
        return sorted(self.info.keys())

    def get_used_disks(self):
        return [dev.disk.devpath for dev in self.devices.values()
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


def _humanize_size(size):
    size = abs(size)
    if size == 0:
        return "0B"
    p = math.floor(math.log(size, 2) / 10)
    return "%.3f%s" % (size / math.pow(1024, p), HUMAN_UNITS[int(p)])


def _dehumanize_size(size):
    # convert human 'size' to integer
    size_in = size
    if size.endswith("B"):
        size = size[:-1]

    # build mpliers based on HUMAN_UNITS
    mpliers = {}
    for (unit, exponent) in zip(HUMAN_UNITS, range(0, len(HUMAN_UNITS))):
        mpliers.update({unit: 2 ** (exponent * 10)})

    num = size
    mplier = 'B'
    for m in mpliers:
        if size.endswith(m):
            mplier = m
            num = size[0:-len(m)]

    try:
        num = float(num)
    except ValueError:
        raise ValueError("'{}' is not valid input.".format(size_in))

    if num < 0:
        raise ValueError("'{}': cannot be negative".format(size_in))

    return int(num * mpliers[mplier])
