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

from collections import OrderedDict
from itertools import count
import logging
import os
import re
import yaml

from .actions import (
    DiskAction,
    PartitionAction,
    FormatAction,
    MountAction,
    RaidAction,
)

log = logging.getLogger("subiquity.filesystem.blockdev")
FIRST_PARTITION_OFFSET = 1 << 20  # 1K offset/aligned
GPT_END_RESERVE = 1 << 20  # save room at the end for GPT


# TODO: Bcachepart class
class Bcachedev():
    # XXX: wanted a per instance counter to track /dev/bcacheX device
    # but not sure how to handle associating multiple backing devices
    # to a cache device, or updated a bcache dev with a cache dev or
    # additional backing devs.
    _ids = count(0)

    def __init__(self, backing, mode):
        self.id = self._ids.next()
        self._path = '/dev/bcache' + int(self.id)
        self._mode = mode  # cache | store
        self._backing = backing

    @property
    def backing(self):
        return self._backing

    @property
    def mode(self):
        return self._mode

    @property
    def path(self):
        return self._path

    def getSize(self, unit='MB'):
        pass


class Disk():
    def __init__(self, devpath, serial, model, parttype, size=0):
        self._devpath = devpath
        self._serial = serial
        self._parttype = parttype
        self._model = model
        self._size = self._get_size(devpath, size)
        self._partitions = OrderedDict()

    def _get_size(self, devpath, size):
        if size:
            return size
        sysblock = os.path.join('/sys/block', os.path.basename(devpath))
        nr_blocks_f = os.path.join(sysblock, 'size')
        block_sz_f = os.path.join(sysblock, 'queue', 'logical_block_size')

        if not os.path.exists(sysblock):
            log.warn('disk at devpath:{} not present'.format(devpath))
            return 0

        with open(nr_blocks_f, 'r') as r:
            nr_blocks = int(r.read())
        with open(block_sz_f, 'r') as r:
            block_sz = int(r.read())

        return nr_blocks * block_sz

    @property
    def devpath(self):
        return self._devpath

    @property
    def serial(self):
        return self._serial

    @property
    def model(self):
        return self._model

    @property
    def parttype(self):
        return self._parttype

    @property
    def size(self):
        return self._size

    @property
    def partitions(self):
        return self._partitions

    def reset(self):
        self._partitions = OrderedDict()
        pass


class Blockdev():
    def __init__(self, devpath, serial, model, parttype='gpt', size=0):
        self.disk = Disk(devpath, serial, model, parttype, size)
        self._filesystems = {}
        self._mounts = {}
        self.bcache = []
        self.lvm = []
        self.holder = {}
        self.baseaction = DiskAction(os.path.basename(self.disk.devpath),
                                     self.disk.model, self.disk.serial,
                                     self.disk.parttype)

    def reset(self):
        ''' Wipe out any actions queued for this disk '''
        self.disk.reset()
        self._filesystems = {}
        self._mounts = {}
        self.bcache = []
        self.lvm = []
        self.holder = {}

    @property
    def devpath(self):
        return self.disk.devpath

    @property
    def mounts(self):
        return self._mounts.values()

    @property
    def parttype(self):
        return self.disk.parttype

    @parttype.setter  # NOQA
    def parttype(self, value):
        self._parttype = value

    @property
    def size(self):
        return self.disk.size

    @property
    def partitions(self):
        return self.disk.partitions

    @property
    def filesystems(self):
        return self._filesystems

    @property
    def percent_free(self):
        ''' return the device free percentage of the whole device'''
        percent = ( int((1.0 - (self.usedspace / self.size)) * 100))
        return percent

    @property
    def available(self):
        ''' return True if has free space or partitions not
            assigned '''
        if not self.is_mounted() and self.percent_free > 0:
            return True
        return False

    @property
    def mounted(self):
        return self.is_mounted()

    @property
    def usedspace(self, unit='b'):
        ''' return amount of used space'''
        space = 0
        for (num, action) in self.disk.partitions.items():
            space += int(action.offset)
            space += int(action.size)

        log.debug('{} usedspace: {}'.format(self.disk.devpath, space))
        return space

    @property
    def freespace(self, unit='B'):
        ''' return amount of free space '''
        used = self.usedspace
        size = self.size
        log.debug('{} freespace: {} - {} = {}'.format(self.disk.devpath,
                                                      size, used,
                                                      size - used))
        return size - used

    @property
    def lastpartnumber(self):
        return len(self.disk.partitions)

    def delete_partition(self, partnum=None, sector=None, mountpoint=None):
        # find part and then call deletePartition()
        # find and remove from self.fstable
        pass

    def add_partition(self, partnum, size, fstype, mountpoint=None, flag=None):
        ''' add a new partition to this disk '''
        log.debug('add_partition:'
                  ' partnum:%s size:%s fstype:%s mountpoint:%s flag=%s' % (
                      partnum, size, fstype, mountpoint, flag))

        if size > self.freespace:
            raise Exception('Not enough space (requested:{} free:{}'.format(
                            size, self.freespace))

        if fstype in ["swap"]:
            fstype = "linux-swap(v1)"

        # round up length by 1M
        def _align_up(size, block_size=1 << 30):
            return size + (block_size - (size % block_size))

        if len(self.disk.partitions) == 0:
            offset = FIRST_PARTITION_OFFSET
        else:
            offset = 0

        log.debug('Aligning start and length on 1M boundaries')
        new_size = _align_up(size + offset)
        if new_size > self.freespace - GPT_END_RESERVE:
            new_size = self.freespace - GPT_END_RESERVE
        log.debug('Old size: {} New size: {}'.format(size, new_size))

        log.debug('requested start: {} length: {}'.format(offset,
                                                          new_size - offset))
        valid_flags = [
            "boot",
            "lvm",
            "raid",
            "bios_grub",
        ]
        if flag and flag not in valid_flags:
            raise Exception('Flag: {} is not valid.'.format(flag))

        # create partition and add
        part_action = PartitionAction(self.baseaction, partnum,
                                      offset, new_size - offset, flag)

        log.debug('PartitionAction:\n{}'.format(part_action.get()))

        self.disk.partitions.update({partnum: part_action})
        partpath = "{}{}".format(self.disk.devpath, partnum)

        # record filesystem formating
        if fstype:
            fs_action = FormatAction(part_action, fstype)
            log.debug('Adding filesystem on {}'.format(partpath))
            log.debug('FormatAction:\n{}'.format(fs_action.get()))
            self.filesystems.update({partpath: fs_action})

        # associate partition devpath with mountpoint
        if mountpoint:
            self._mounts[partpath] = mountpoint

        log.debug('Partition Added')
        return new_size

    def set_holder(self, devpath, holdtype):
        self.holder[holdtype] = devpath

    def is_mounted(self):
        with open('/proc/mounts') as pm:
            mounts = pm.read()

        # collect any /dev/* device and use
        # dict to uniq the list of devices mounted
        mounted_devs = {}
        for mnt in re.findall('/dev/.*', mounts):
            log.debug('mnt={}'.format(mnt))
            (devpath, mount, *_) = mnt.split()
            # resolve any symlinks
            mounted_devs.update(
                {os.path.realpath(devpath): mount})

        log.debug('mounted_devs: {}'.format(mounted_devs))
        matches = [dev for dev in mounted_devs.keys()
                   if dev.startswith(self.disk.devpath)]
        log.debug('Checking if {} is in {}'.format(
                  self.disk.devpath, matches))
        if len(matches) > 0:
            log.debug('Device is mounted: {}'.format(matches))
            return True

        return False

    def get_actions(self):
        if self.is_mounted():
            log.debug('Emitting no actions, device is mounted')
            return []

        actions = []
        action = self.baseaction.get()
        for (num, part) in self.disk.partitions.items():
            partpath = "{}{}".format(self.disk.devpath, part.partnum)
            actions.append(part)
            if partpath in self.filesystems:
                format_action = self.filesystems[partpath]
                actions.append(format_action)

            if partpath in self._mounts:
                mount_action = MountAction(format_action,
                                           self._mounts[partpath])
                actions.append(mount_action)

        return self.sort_actions([action] + [a.get() for a in actions])

    def sort_actions(self, actions):
        def type_index(t):
            order = ['disk', 'partition', 'raid', 'format', 'mount']
            return order.index(t.get('type'))

        def path_count(p):
            return p.get('path').count('/')

        def order_sort(a):
            # sort by type first
            score = type_index(a)
            # for type==mount, count the number of dirs
            if a.get('type') == 'mount':
                score += path_count(a)
            return score

        actions = sorted(actions, key=order_sort)

        return actions

    def get_fs_table(self):
        ''' list(mountpoint, humansize, fstype, partition_path) '''
        fs_table = []
        for (num, part) in self.disk.partitions.items():
            partpath = "{}{}".format(self.disk.devpath, part.partnum)
            if partpath in self.filesystems:
                fs = self.filesystems[partpath]
                mntpoint = self._mounts.get(partpath, fs.fstype)
                fs_table.append(
                    (mntpoint, part.size, fs.fstype, partpath))

        return fs_table


class Raiddev(Blockdev):
    def __init__(self, devpath, serial, model, parttype, size,
                 raid_level, raid_devices, spare_devices):
        super().__init__(devpath, serial, model, parttype, size)
        self._raid_devices = raid_devices
        self._raid_level = raid_level
        self._spare_devices = spare_devices
        self.baseaction = RaidAction(os.path.basename(self.disk.devpath),
                                     self._raid_devices,
                                     self._raid_level,
                                     self._spare_devices)


if __name__ == '__main__':
    def get_filesystems(devices):
        print("FILE SYSTEM")
        for dev in devices:
            for mnt, size, fstype, path in dev.get_fs_table():
                print("{}\t\t{} Gb\t{}\t{}".format(mnt, size, fstype, path))

    def get_used_disks(devices):
        print("USED DISKS")

    devices = []
    #Blockdev(devpath, serial, model, parttype='gpt'):
    GB = 1 << 30
    sda = Blockdev('/dev/sda', 'QM_TARGET_01', 'QEMU SSD DISK',
                   parttype='gpt', size=128 * GB)
    sdb = Blockdev('/dev/sdb', 'dafunk', 'QEMU SPINNER', size=500 * GB)

    print(sda.freespace)
    sda.add_partition(1, 8 * 1024 * 1024 * 1024, 'ext4', '/', 'bios_grub')
    print(sda.freespace)
    sda.add_partition(2, 2 * 1024 * 1024 * 1024, 'ext4', '/home')
    print(sda.freespace)
    sdb.add_partition(1, 50 * 1024 * 1024 * 1024, 'btrfs', '/opt')

    get_filesystems([sda, sdb])
    print()
    HEADER = '''
reporter:
 subiquity:
  path: /tmp/curtin_progress_subiquity
  progress: True

partitioning_commands:
 builtin: curtin block-meta custom
'''
    print(HEADER)

    actions = {'storage': sda.get_actions() + sdb.get_actions()}
    print(yaml.dump(actions, default_flow_style=False))
