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

import os
import parted
import yaml
import logging
from itertools import count

from subiquity.filesystem.actions import (
    DiskAction,
    PartitionAction,
    FormatAction,
    MountAction
)

log = logging.getLogger("subiquity.filesystem.blockdev")


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
        if type(self._backing) == parted.disk.Disk:
            return self._backing.device.getSize(unit=unit)
        else:
            return self._backing.getSize(unit=unit)


class Blockdev():
    def __init__(self, devpath, serial, parttype='msdos'):
        self.serial = serial
        self.devpath = devpath
        self._parttype = parttype
        self.device = parted.getDevice(self.devpath)
        self.disk = parted.freshDisk(self.device, self.parttype)
        self.mounts = {}
        self.bcache = []
        self.lvm = []

    def _get_largest_free_region(self):
        """Finds largest free region on the disk"""
        # There are better ways to do it, but let's be straightforward
        max_size = -1
        region = None

        alignment = self.device.optimumAlignment

        for r in self.disk.getFreeSpaceRegions():
            # Heuristic: Ignore alignment gaps
            if r.length > max_size and r.length > alignment.grainSize:
                region = r
                max_size = r.length

        return region

    @property
    def parttype(self):
        return self._parttype

    @parttype.setter  # NOQA
    def parttype(self, value):
        self._parttype = value

    @property
    def available(self):
        ''' return True if has free space or partitions not
            assigned '''
        if self.freespace > 0.0 or self.freepartition > 0.0:
            return True
        return False

    @property
    def freespace(self, unit='b'):
        ''' return amount of free space '''
        return sum([geo.getSize(unit=unit) for geo in
                    self.disk.getFreeSpaceRegions()])

    @property
    def freepartition(self, unit='b'):
        ''' return amount of partitionable space'''
        return sum([part.geometry.getSize(unit=unit) for part in
                    self.disk.getFreeSpacePartitions()])

    @property
    def lastpartnumber(self):
        return self.disk.lastPartitionNumber

    def delete_partition(self, partnum=None, sector=None, mountpoint=None):
        # find part and then call deletePartition()
        # find and remove from self.fstable
        pass

    def add_partition(self, partnum, size, fstype, mountpoint, flag=None):
        ''' add a new partition to this disk '''
        if size > self.freepartition:
            raise Exception('Not enough space')

            if fstype in ["swap"]:
                fstype = "linux-swap(v1)"

        geometry = self._get_largest_free_region()
        if not geometry:
            raise Exception('No free sectors available')

        # convert size into a geometry based on existing partitions
        try:
            start = self.disk.partitions[-1].geometry.end + 1
        except IndexError:
            start = 0
        length = parted.sizeToSectors(size, 'B', self.device.sectorSize)
        req_geo = parted.Geometry(self.device, start=start, length=length)

        # find common area
        parttype = parted.PARTITION_NORMAL
        alignment = self.device.optimalAlignedConstraint
        geometry = geometry.intersect(req_geo)
        # update geometry with alignment
        constraint = parted.Constraint(maxGeom=geometry).intersect(alignment)
        data = {
            'start': constraint.startAlign.alignUp(geometry, geometry.start),
            'end': constraint.endAlign.alignDown(geometry, geometry.end),
        }
        geometry = parted.Geometry(device=self.device,
                                   start=data['start'],
                                   end=data['end'])
        # create partition
        if fstype not in ['bcache cache', 'bcache store']:
            fs = parted.FileSystem(type=fstype, geometry=geometry)
        else:
            fs = None
        partition = parted.Partition(disk=self.disk, type=parttype,
                                     fs=fs, geometry=geometry)

        # add flags
        flags = {
            "boot": parted.PARTITION_BOOT,
            "lvm": parted.PARTITION_LVM,
            "raid": parted.PARTITION_RAID,
            "bios_grub": parted.PARTITION_BIOS_GRUB
        }
        if flag in flags:
            partition.setFlag(flags[flag])

        self.disk.addPartition(partition=partition, constraint=constraint)

        # fetch the newly created partition
        partpath = "{}{}".format(self.disk.device.path, partition.number)
        newpart = self.disk.getPartitionByPath(partpath)

        # create bcachedev if neded
        if fstype.startswith('bcache'):
            mode = fstype.split()[-1]
            self.bcache.append(Bcachedev(backing=newpart, mode=mode))

        # associate partition devpath with mountpoint
        if mountpoint:
            self.mounts[partpath] = mountpoint

    def get_actions(self):
        actions = []
        baseaction = DiskAction(os.path.basename(self.disk.device.path),
                                self.device.model, self.serial, self.parttype)
        action = baseaction.get()
        for part in self.disk.partitions:
            fs_size = int(part.getSize(unit='B'))
            if part.fileSystem:
                fs_type = part.fileSystem.type
            else:
                fs_type = None
            flags = part.getFlagsAsString()

            partition_action = PartitionAction(baseaction,
                                               part.number,
                                               fs_size, flags)
            actions.append(partition_action)
            if fs_type:
                format_action = FormatAction(partition_action,
                                             fs_type)
                actions.append(format_action)
                mountpoint = self.mounts[part.path]
                mount_action = MountAction(format_action, mountpoint)
                actions.append(mount_action)

        return [action] + [a.get() for a in actions]

    def get_fs_table(self):
        ''' list(mountpoint, humansize, fstype, partition_path) '''
        fs_table = []
        for part in self.disk.partitions:
            if part.fileSystem:
                mntpoint = self.mounts[part.path]
                fs_size = int(part.getSize(unit='GB'))
                fs_type = part.fileSystem.type
                devpath = part.path
                fs_table.append(
                    (mntpoint, fs_size, fs_type, devpath))

        return fs_table


if __name__ == '__main__':
    def get_filesystems(devices):
        print("FILE SYSTEM")
        for dev in devices:
            for mnt, size, fstype, path in dev.get_fs_table():
                print("{}\t\t{} Gb\t{}\t{}".format(mnt, size, fstype, path))

    def get_used_disks(devices):
        print("USED DISKS")

    devices = []
    sda = Blockdev('/dev/sda', 'QM_TARGET_01', parttype='gpt')
    sdb = Blockdev('/dev/sdb', 'dafunk')

    sda.add_partition(1, 8 * 1024 * 1024 * 1024, 'ext4', '/', 'bios_grub')
    sda.add_partition(2, 2 * 1024 * 1024 * 1024, 'ext4', '/home')
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
