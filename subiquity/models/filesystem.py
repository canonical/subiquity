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
import os
import re

from .blockdev import (Bcachedev,
                       Blockdev,
                       LVMDev,
                       Raiddev,
                       sort_actions)
import math
from subiquity.model import ModelPolicy


HUMAN_UNITS = ['B', 'K', 'M', 'G', 'T', 'P']
log = logging.getLogger('subiquity.models.filesystem')


class AttrDict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class FilesystemModel(ModelPolicy):
    """ Model representing storage options
    """
    base_signal = 'menu:filesystem:main'
    signals = [
        ('Filesystem view',
         base_signal,
         'filesystem'),
        ('Filesystem error',
         'filesystem:error',
         'filesystem_error'),
        ('Filesystem finish',
         'filesystem:finish',
         'filesystem_handler'),
        ('Show disk partition view',
         base_signal + ':show-disk-partition',
         'disk_partition'),
        ('Finish disk partition',
         'filesystem:finish-disk-partition',
         'disk_partition_handler'),
        ('Add disk partition',
         base_signal + ':add-disk-partition',
         'add_disk_partition'),
        ('Finish add disk partition',
         'filesystem:finish-add-disk-partition',
         'add_disk_partition_handler'),
        ('Finish whole disk format/mount',
         'filesystem:finish-add-disk-format',
         'add_disk_format_handler'),
        ('Format or create swap on entire device (unusual, advanced)',
         base_signal + ':create-swap-entire-device',
         'create_swap_entire_device'),
        ('Show disk information',
         base_signal + ':show-disk-information',
         'show_disk_information'),
        ('Show next disk information',
         'filesystem:show-disk-info-next',
         'show_disk_information_next'),
        ('Show prev disk information',
         'filesystem:show-disk-info-prev',
         'show_disk_information_prev'),
        ('Add Raid Device',
         'filesystem:add-raid-dev',
         'add_raid_dev'),
    ]

    fs_menu = [
        # ('Connect iSCSI network disk',
        #  'filesystem:connect-iscsi-disk',
        #  'connect_iscsi_disk'),
        # ('Connect Ceph network disk',
        #  'filesystem:connect-ceph-disk',
        #  'connect_ceph_disk'),
        ('Create volume group (LVM2)',
         base_signal + ':create-volume-group',
         'create_volume_group'),
        ('Create software RAID (MD)',
         base_signal + ':create-raid',
         'create_raid'),
        ('Setup hierarchichal storage (bcache)',
         base_signal + ':setup-bcache',
         'create_bcache'),
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

    partition_flags = [
        'boot',
        'lvm',
        'raid',
        'bios_grub',
    ]

    # TODO: what is "linear" level?
    raid_levels = [
        "0",
        "1",
        "5",
        "6",
        "10",
    ]

    # th following blocktypes cannot be partitioned
    no_partition_blocktypes = [
        "bcache",
        "lvm_partition",
        "lvm_volgroup",
        "raid",
    ]

    def __init__(self, prober, opts):
        self.opts = opts
        self.prober = prober
        self.info = {}
        self.devices = {}
        self.raid_devices = {}
        self.bcache_devices = {}
        self.lvm_devices = {}
        self.storage = {}
        self.holders = {}
        self.tags = {}

    def reset(self):
        log.debug('FilesystemModel: resetting disks')
        self.devices = {}
        self.info = {}
        self.raid_devices = {}
        self.bcache_devices = {}
        self.lvm_devices = {}
        self.holders = {}
        self.tags = {}

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
        '''get disk object given path.  If provided a partition, then
         return the parent disk.  /dev/sda2 --> /dev/sda obj'''
        log.debug('probe_storage: get_disk({})'.format(disk))

        if not disk.startswith('/dev/'):
            disk = os.path.join('/dev', disk)

        if disk not in self.devices:
            try:
                self.devices[disk] = Blockdev(disk, self.info[disk].serial,
                                              self.info[disk].model,
                                              size=self.info[disk].size)
            except KeyError:
                ''' if it looks like a partition, try again with
                    parent device '''
                if disk[-1].isdigit():
                    return self.get_disk(re.split('[\d+]', disk)[0])

        return self.devices[disk]

    def get_available_disks(self):
        ''' currently only returns available disks '''
        disks = [d for d in self.get_all_disks()
                 if (d.available and
                     len(self.get_holders(d.devpath)) == 0)]
        log.debug('get_available_disks -> {}'.format(
                  ",".join([d.devpath for d in disks])))
        return disks

    def get_all_disks(self):
        possible_devices = list(set(list(self.devices.keys()) +
                                    list(self.info.keys())))
        possible_disks = [self.get_disk(d) for d in sorted(possible_devices)]
        log.debug('get_all_disks -> {}'.format(",".join([d.devpath for d in
                                                         possible_disks])))
        return possible_disks

    def calculate_raid_size(self, raid_level, raid_devices, spare_devices):
        '''
            0: array size is the size of the smallest component partition times
               the number of component partitions
            1: array size is the size of the smallest component partition
            5: array size is the size of the smallest component partition times
               the number of component partitions munus 1
            6: array size is the size of the smallest component partition times
               the number of component partitions munus 2
        '''
        # https://raid.wiki.kernel.org/ \
        #       index.php/RAID_superblock_formats#Total_Size_of_superblock
        # Version-1 superblock format on-disk layout:
        # Total size of superblock: 256 Bytes plus 2 bytes per device in the
        # array
        log.debug('calc_raid_size: level={} rd={} sd={}'.format(raid_level,
                                                                raid_devices,
                                                                spare_devices))
        overhead_bytes = 256 + (2 * (len(raid_devices) + len(spare_devices)))
        log.debug('calc_raid_size: overhead_bytes={}'.format(overhead_bytes))

        # find the smallest device
        min_dev_size = min([d.size for d in raid_devices])
        log.debug('calc_raid_size: min_dev_size={}'.format(min_dev_size))

        if raid_level == 0:
            array_size = min_dev_size * len(raid_devices)
        elif raid_level == 1:
            array_size = min_dev_size
        elif raid_level == 5:
            array_size = min_dev_size * (len(raid_devices) - 1)
        elif raid_level == 10:
            array_size = min_dev_size * int((len(raid_devices) /
                                             len(spare_devices)))
        total_size = array_size - overhead_bytes
        log.debug('calc_raid_size: array_size:{} - overhead:{} = {}'.format(
                  array_size, overhead_bytes, total_size))
        return total_size

    def add_raid_device(self, raidspec):
        # assume raidspec has already been valided in view/controller
        log.debug('Attempting to create a raid device')
        '''
        raidspec = {
            'devices': ['/dev/sdb     1.819T, HDS5C3020ALA632',
                        '/dev/sdc     1.819T, 001-9YN164',
                        '/dev/sdf     1.819T, 001-9YN164',
                        '/dev/sdg     1.819T, 001-9YN164',
                        '/dev/sdh     1.819T, HDS5C3020ALA632',
                        '/dev/sdi     1.819T, 001-9YN164'],
                        '/dev/sdj     1.819T, Unknown Model'],
            'raid_level': '0',
            'hot_spares': '0',
            'chunk_size': '4K',
        }
        could be /dev/sda1, /dev/md0, /dev/bcache1, /dev/vg_foo/foobar2?
        '''
        raid_devices = []
        spare_devices = []
        all_devices = [r.split() for r in raidspec.get('devices', [])]
        nr_spares = int(raidspec.get('hot_spares'))

        # XXX: curtin requires a partition table on the base devices
        # and then one partition of type raid
        for (devpath, *_) in all_devices:
            disk = self.get_disk(devpath)

            # add or update a partition to be raid type
            if disk.path != devpath:  # we must have got a partition
                raiddev = disk.get_partition(devpath)
                raiddev.flags = 'raid'
            else:
                disk.add_partition(1, disk.freespace, None, None, flag='raid')
                raiddev = disk

            if len(raid_devices) + nr_spares < len(all_devices):
                raid_devices.append(raiddev)
            else:
                spare_devices.append(raiddev)

        # auto increment md number based in registered devices
        raid_shortname = 'md{}'.format(len(self.raid_devices))
        raid_dev_name = '/dev/' + raid_shortname
        raid_serial = '{}_serial'.format(raid_dev_name)
        raid_model = '{}_model'.format(raid_dev_name)
        raid_parttype = 'gpt'
        raid_level = int(raidspec.get('raid_level'))
        raid_size = self.calculate_raid_size(raid_level, raid_devices,
                                             spare_devices)

        # create a Raiddev (pass in only the names)
        raid_parts = []
        for dev in raid_devices:
            self.set_holder(dev.devpath, raid_dev_name)
            self.set_tag(dev.devpath, 'member of MD ' + raid_shortname)
            for num, action in dev.partitions.items():
                raid_parts.append(action.action_id)
        spare_parts = []
        for dev in spare_devices:
            self.set_holder(dev.devpath, raid_dev_name)
            self.set_tag(dev.devpath, 'member of MD ' + raid_shortname)
            for num, action in dev.partitions.items():
                spare_parts.append(action.action_id)

        raid_dev = Raiddev(raid_dev_name, raid_serial, raid_model,
                           raid_parttype, raid_size,
                           raid_parts,
                           raid_level,
                           spare_parts)

        # add it to the model's info dict
        raid_dev_info = {
            'type': 'disk',
            'name': raid_dev_name,
            'size': raid_size,
            'serial': raid_serial,
            'vendor': 'Linux Software RAID',
            'model': raid_model,
            'is_virtual': True,
            'raw': {
                'MAJOR': '9',
            },
        }
        self.info[raid_dev_name] = AttrDict(raid_dev_info)

        # add it to the model's raid devices
        self.raid_devices[raid_dev_name] = raid_dev
        # add it to the model's devices
        self.add_device(raid_dev_name, raid_dev)

        log.debug('Successfully added raid_dev: {}'.format(raid_dev))

    def add_lvm_volgroup(self, lvmspec):
        log.debug('Attempting to create an LVM volgroup device')
        '''
        lvm_volgroup_spec = {
            'volgroup': 'my_volgroup_name',
            'devices': ['/dev/sdb     1.819T, HDS5C3020ALA632']
        }
        '''
        lvm_shortname = lvmspec.get('volgroup')
        lvm_dev_name = '/dev/' + lvm_shortname
        lvm_serial = '{}_serial'.format(lvm_dev_name)
        lvm_model = '{}_model'.format(lvm_dev_name)
        lvm_parttype = 'gpt'
        lvm_devices = []

        # extract just the device name for disks in this volgroup
        all_devices = [r.split() for r in lvmspec.get('devices', [])]

        # XXX: curtin requires a partition table on the base devices
        # and then one partition of type lvm
        for (devpath, *_) in all_devices:
            disk = self.get_disk(devpath)

            self.set_holder(devpath, lvm_dev_name)
            self.set_tag(devpath, 'member of LVM ' + lvm_shortname)

            # add or update a partition to be raid type
            if disk.path != devpath:  # we must have got a partition
                pv_dev = disk.get_partition(devpath)
                pv_dev.flags = 'lvm'
            else:
                disk.add_partition(1, disk.freespace, None, None, flag='lvm')
                pv_dev = disk

            lvm_devices.append(pv_dev)

        lvm_size = sum([pv.size for pv in lvm_devices])
        lvm_device_names = [pv.id for pv in lvm_devices]

        log.debug('lvm_devices: {}'.format(lvm_device_names))
        lvm_dev = LVMDev(lvm_dev_name, lvm_serial, lvm_model,
                         lvm_parttype, lvm_size,
                         lvm_shortname, lvm_device_names)
        log.debug('{} volgroup: {} devices: {}'.format(lvm_dev.id,
                                                       lvm_dev.volgroup,
                                                       lvm_dev.devices))

        # add it to the model's info dict
        lvm_dev_info = {
            'type': 'disk',
            'name': lvm_dev_name,
            'size': lvm_size,
            'serial': lvm_serial,
            'vendor': 'Linux Volume Group (LVM2)',
            'model': lvm_model,
            'is_virtual': True,
            'raw': {
                'MAJOR': '9',
            },
        }
        self.info[lvm_dev_name] = AttrDict(lvm_dev_info)

        # add it to the model's lvm devices
        self.lvm_devices[lvm_dev_name] = lvm_dev
        # add it to the model's devices
        self.add_device(lvm_dev_name, lvm_dev)

        log.debug('Successfully added lvm_dev: {}'.format(lvm_dev))

    def add_bcache_device(self, bcachespec):
        # assume bcachespec has already been valided in view/controller
        log.debug('Attempting to create a bcache device')
        '''
        bcachespec = {
            'backing_device': '/dev/sdc     1.819T, 001-9YN164',
            'cache_device': '/dev/sdb     1.819T, HDS5C3020ALA632',
        }
        could be /dev/sda1, /dev/md0, /dev/vg_foo/foobar2?
        '''
        backing_device = self.get_disk(bcachespec['backing_device'].split()[0])
        cache_device = self.get_disk(bcachespec['cache_device'].split()[0])

        # auto increment md number based in registered devices
        bcache_shortname = 'bcache{}'.format(len(self.bcache_devices))
        bcache_dev_name = '/dev/' + bcache_shortname
        bcache_serial = '{}_serial'.format(bcache_dev_name)
        bcache_model = '{}_model'.format(bcache_dev_name)
        bcache_parttype = 'gpt'
        bcache_size = backing_device.size

        # create a Bcachedev (pass in only the names)
        bcache_dev = Bcachedev(bcache_dev_name, bcache_serial, bcache_model,
                               bcache_parttype, bcache_size,
                               backing_device, cache_device)

        # mark bcache holders
        self.set_holder(backing_device.devpath, bcache_dev_name)
        self.set_holder(cache_device.devpath, bcache_dev_name)

        # tag device use
        self.set_tag(backing_device.devpath,
                     'backing store for ' + bcache_shortname)
        cache_tag = self.get_tag(cache_device.devpath)
        if len(cache_tag) > 0:
            cache_tag += ", " + bcache_shortname
        else:
            cache_tag = "cache for " + bcache_shortname
        self.set_tag(cache_device.devpath, cache_tag)

        # add it to the model's info dict
        bcache_dev_info = {
            'type': 'disk',
            'name': bcache_dev_name,
            'size': bcache_size,
            'serial': bcache_serial,
            'vendor': 'Linux bcache',
            'model': bcache_model,
            'is_virtual': True,
            'raw': {
                'MAJOR': '9',
            },
        }
        self.info[bcache_dev_name] = AttrDict(bcache_dev_info)

        # add it to the model's bcache devices
        self.bcache_devices[bcache_dev_name] = bcache_dev
        # add it to the model's devices
        self.add_device(bcache_dev_name, bcache_dev)

        log.debug('Successfully added bcache_dev: {}'.format(bcache_dev))

    def get_bcache_cachedevs(self):
        ''' return uniq list of bcache cache devices '''
        cachedevs = list(set([bcache_dev.cache_device for bcache_dev in
                              self.bcache_devices.values()]))
        log.debug('bcache cache devs: {}'.format(cachedevs))
        return cachedevs

    def add_device(self, devpath, device):
        log.debug("adding device: {} = {}".format(devpath, device))
        self.devices[devpath] = device

    def get_partitions(self):
        log.debug('probe_storage: get_partitions()')
        partitions = []
        for dev in self.devices.values():
            partnames = [part.devpath for (num, part) in
                         dev.disk.partitions.items()]
            partitions += partnames

        partitions = sorted(partitions)
        log.debug('probe_storage: get_partitions() returns: {}'.format(
                  partitions))
        return partitions

    def get_filesystems(self):
        log.debug('get_fs')
        fs = []
        for dev in self.devices.values():
            fs += dev.filesystems

        return fs

    def installable(self):
        ''' one or more disks has used space
            and has "/" as a mount
        '''
        for disk in self.get_all_disks():
            if disk.usedspace > 0 and "/" in disk.mounts:
                return True

        return False

    def bootable(self):
        ''' true if one disk has a boot partition '''
        log.debug('bootable check')
        for disk in self.get_all_disks():
            for (num, action) in disk.partitions.items():
                if action.flags in ['bios_grub']:
                    log.debug('bootable check: we\'ve got boot!')
                    return True

        log.debug('bootable check: no disks have been marked bootable')
        return False

    def set_holder(self, held_device, holder_devpath):
        ''' insert a hold on `held_device' by adding `holder_devpath' to
            a list at self.holders[`held_device']
        '''
        if held_device not in self.holders:
            self.holders[held_device] = [holder_devpath]
        else:
            self.holders[held_device].append(holder_devpath)

    def clear_holder(self, held_device, holder_devpath):
        if held_device in self.holders:
            self.holders[held_device].remove(holder_devpath)

    def get_holders(self, held_device):
        return self.holders.get(held_device, [])

    def set_tag(self, device, tag):
        self.tags[device] = tag

    def get_tag(self, device):
        return self.tags.get(device, '')

    def valid_mount(self, format_spec):
        """ format spec

        {
          'fstype' Str(ext4|btrfs..,
          'mountpoint': Str
        }
        """
        log.debug('valid_mount: spec: {}'.format(format_spec))
        # if user is not formatting, ignore mountpoint
        fmt = format_spec.get('fstype')
        if fmt in ['leave unformatted']:
            format_spec['mountpoint'] = None
            return True

        mountpoint = format_spec.get('mountpoint')
        if not mountpoint:
            raise ValueError('Is None')

        # If the value is in error state, return the
        # the same error
        err_prefix = 'error: '
        if mountpoint.lower().startswith(err_prefix):
            mountpoint = mountpoint[len(err_prefix):]
            raise ValueError(mountpoint)

        if not mountpoint.startswith('/'):
            raise ValueError('Does not start with /')

        # remove redundent // and ..
        mountpoint = os.path.realpath(mountpoint)

        # /usr/include/linux/limits.h:PATH_MAX
        if len(mountpoint) > 4095:
            raise ValueError('Path exceeds PATH_MAX')

        all_mounts = self.get_mounts()
        if mountpoint in all_mounts:
            raise ValueError('Already mounted')

        return True

    def get_empty_disks(self):
        ''' empty disk is one that does not have any
            partitions, filesystems or mounts, and is non-zero size '''
        empty = []
        for dev in self.get_available_disks():
            if len(dev.partitions) == 0 and \
               len(dev.mounts) == 0 and \
               len(dev.filesystems) == 0:
                empty.append(dev)
        log.debug('empty_disks: {}'.format(
                  ", ".join([dev.path for dev in empty])))
        return empty

    def get_empty_disk_names(self):
        return [dev.disk.devpath for dev in self.get_empty_disks()]

    def get_empty_partition_names(self):
        ''' empty partitions have non-zero size, but are not part
            of a filesystem or mount point or other raid '''
        empty = []
        for dev in self.get_available_disks():
            empty += dev.available_partitions

        log.debug('empty_partitions: {}'.format(", ".join(empty)))
        return empty

    def get_available_disk_names(self):
        return [dev.disk.devpath for dev in self.get_available_disks()]

    def get_used_disk_names(self):
        return [dev.disk.devpath for dev in self.get_all_disks()
                if dev.available is False]

    def get_disk_info(self, disk):
        return self.info.get(disk, {})

    def get_mounts(self):
        mounts = []
        for dev in self.get_all_disks():
            mounts += dev.mounts

        return mounts

    def get_disk_action(self, disk):
        return self.devices[disk].get_actions()

    def get_actions(self):
        actions = []
        for dev in self.devices.values():
            # don't write out actions for devices not in use
            if not dev.available:
                actions += dev.get_actions()

        log.debug('****')
        log.debug('all actions:{}'.format(actions))
        log.debug('****')
        return sort_actions(actions)


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
