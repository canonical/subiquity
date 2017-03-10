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

import glob
import json
import logging
import math
import os
import re

from .blockdev import (Bcachedev,
                       Blockdev,
                       LVMDev,
                       Raiddev,
                       sort_actions)


HUMAN_UNITS = ['B', 'K', 'M', 'G', 'T', 'P']
log = logging.getLogger('subiquity.models.filesystem')


class AttrDict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class FS:
    def __init__(self, label, is_mounted):
        self.label = label
        self.is_mounted = is_mounted

class FilesystemModel(object):
    """ Model representing storage options
    """

    supported_filesystems = [
        ('ext4', True, FS('ext4', True)),
        ('xfs', True, FS('xfs', True)),
        ('btrfs', True, FS('btrfs', True)),
        ('---', False),
        ('swap', True, FS('swap', False)),
        ('bcache cache', True, FS('bcache cache', False)),
        ('bcache store', True, FS('bcache store', False)),
        ('---', False),
        ('leave unformatted', True, FS('leave unformatted', False)),
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

    def probe_storage(self):
        log.debug('model.probe_storage: probing storage')
        storage = self.prober.get_storage()
        log.debug('got storage:\n{}'.format(storage))
        # TODO: Put this into a logging namespace for probert
        #       since its quite a bit of log information.
        # log.debug('storage probe data:\n{}'.format(
        #          json.dumps(self.storage, indent=4, sort_keys=True)))

        # TODO: replace this with Storage.get_device_by_match()
        # which takes a lambda fn for matching
        VALID_MAJORS = ['8', '253']
        for disk in storage.keys():
            if storage[disk]['DEVTYPE'] == 'disk' and \
               storage[disk]['MAJOR'] in VALID_MAJORS:
                log.debug('disk={}\n{}'.format(disk,
                          json.dumps(storage[disk], indent=4,
                                     sort_keys=True)))
                self.info[disk] = self.prober.get_storage_info(disk)

    def get_disk(self, disk):
        '''get disk object given path.  If provided a partition, then
         return the parent disk.  /dev/sda2 --> /dev/sda obj'''
        log.debug('probe_storage: get_disk({})'.format(disk))

        if not disk.startswith('/dev/'):
            disk = os.path.join('/dev', disk)

        if disk not in self.devices:
            info = self.info.get(disk)
            if info is not None:
                self.devices[disk] = Blockdev(disk, info.serial, info.model, size=info.size)
            else:
                ''' if it looks like a partition, try again with
                    parent device '''
                # This is crazy, we should remove this fallback asap.
                if disk[-1].isdigit():
                    return self.get_disk(re.split('[\d+]', disk)[0])
                else:
                    raise KeyError(disk)

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

    def validate_mount(self, mountpoint):
        if mountpoint is None:
            return
        # /usr/include/linux/limits.h:PATH_MAX
        if len(mountpoint) > 4095:
            return 'Path exceeds PATH_MAX'
        mnts = self.get_mounts()
        dev = mnts.get(mountpoint)
        if dev is not None:
            return "%s is already mounted at %s"%(dev, mountpoint)

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
        """Return a dict mapping mountpoint to device."""
        r = {}
        for dev in self.get_all_disks():
            for k, v in dev._mounts.items():
                r[v] = k

        return r

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
        mpliers[unit] = 2 ** (exponent * 10)

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


import collections
import attr


def id_factory(name):
    i = 0
    def factory():
        nonlocal i
        r = "%s-%s"%(name, i)
        i += 1
        return r
    return attr.Factory(factory)

def asdict(inst):
    r = collections.OrderedDict()
    for field in attr.fields(type(inst)):
        if field.name.startswith('_'):
            continue
        v = getattr(inst, field.name)
        if v:
            if hasattr(v, 'id'):
                v = v.id
            r[field.name] = v
    return r

@attr.s
class Disk:
    id = attr.ib(default=id_factory("disk"))
    type = attr.ib(default="disk")
    ptable = attr.ib(default='gpt')
    serial = attr.ib(default=None)
    path = attr.ib(default=None)
    model = attr.ib(default=None)
    wipe = attr.ib(default=None)
    preserve = attr.ib(default=False)
    name = attr.ib(default="")
    grub_device = attr.ib(default=False)
    _partitions = attr.ib(default=attr.Factory(list), repr=False)
    _fs = attr.ib(default=None, repr=False)
    _info = attr.ib(default=None)

    @classmethod
    def from_info(self, info):
        d = Disk(info=info)
        d.serial = info.serial
        d.path = info.name
        d.model = info.model
        return d

    @property
    def available(self):
        return self.used < self.size

    @property
    def next_partnum(self):
        return len(self._partitions) + 1

    @property
    def size(self):
        return self._info.size

    @property
    def used(self):
        if self._fs is not None:
            return self.size
        r = 0
        for p in self._partitions:
            r += p.size
        return r

    @property
    def free(self):
        return self.size - self.used

@attr.s
class Partition:
    id = attr.ib(default=id_factory("part"))
    type = attr.ib(default="partition")
    number = attr.ib(default=0)
    device = attr.ib(default=None)
    size = attr.ib(default=None)
    wipe = attr.ib(default=None)
    flag = attr.ib(default=None)
    preserve = attr.ib(default=False)

    _fs = attr.ib(default=None, repr=False)

    @property
    def available(self):
        return self._fs is None or self._fs._mount is None

    @property
    def path(self):
        return "%s%s"%(self.device.path, self.number)

    def render(self):
        r = asdict(self)
        r['device'] = self.device.id
        return r

@attr.s
class Filesystem:
    id = attr.ib(default=id_factory("fs"))
    type = attr.ib(default="format")
    fstype = attr.ib(default=None)
    volume = attr.ib(default=None) # validator=attr.validators.instance_of((Partition, Disk, type(None))), 
    label = attr.ib(default=None)
    uuid = attr.ib(default=None)
    preserve = attr.ib(default=False)
    _mount = attr.ib(default=None, repr=False)

    def render(self):
        r = asdict(self)
        r['volume'] = self.volume.id
        return r

@attr.s
class Mount:
    id = attr.ib(default=id_factory("mount"))
    type = attr.ib(default="mount")
    device = attr.ib(default=None) # validator=attr.validators.instance_of((Filesystem, type(None))), 
    path = attr.ib(default=None)

    def render(self):
        r = asdict(self)
        r['device'] = self.device.id
        return r


class FilesystemModel(object):

    supported_filesystems = [
        ('ext4', True, FS('ext4', True)),
        ('xfs', True, FS('xfs', True)),
        ('btrfs', True, FS('btrfs', True)),
        ('---', False),
        ('swap', True, FS('swap', False)),
        ('bcache cache', True, FS('bcache cache', False)),
        ('bcache store', True, FS('bcache store', False)),
        ('---', False),
        ('leave unformatted', True, FS('leave unformatted', False)),
    ]

    def __init__(self, prober, opts):
        self.prober = prober
        self.opts = opts
        self._available_disks = {} # keyed by path, eg /dev/sda
        self.reset()

    def reset(self):
        self._disks = collections.OrderedDict() # only gets populated when something uses the disk
        self._filesystems = []
        self._partitions = []
        self._mounts = []

    def render(self):
        r = []
        for d in self._disks.values():
            r.append(asdict(d))
        for p in self._partitions:
            r.append(asdict(p))
        for f in self._filesystems:
            r.append(asdict(f))
        for m in self._mounts:
            r.append(asdict(m))
        return r

    def _get_system_mounted_disks(self):
        # This assumes a fairly vanilla setup. It won't list as
        # mounted a disk that is only mounted via lvm, for example.
        mounted_devs = []
        with open('/proc/mounts') as pm:
            for line in pm:
                if line.startswith('/dev/'):
                    mounted_devs.append(line.split()[0][5:])
        mounted_disks = set()
        for dev in mounted_devs:
            if os.path.exists('/sys/block/{}'.format(dev)):
                mounted_disks.add('/dev/' + dev)
            else:
                paths = glob.glob('/sys/block/*/{}/partition'.format(dev))
                if len(paths) == 1:
                    mounted_disks.add('/dev/' + paths[0].split('/')[3])
        return mounted_disks

    def probe(self):
        storage = self.prober.get_storage()
        VALID_MAJORS = ['8', '253']
        currently_mounted = self._get_system_mounted_disks()
        for path, data in storage.items():
            if path in currently_mounted:
                continue
            if data['DEVTYPE'] == 'disk' and data['MAJOR'] in VALID_MAJORS:
                #log.debug('disk={}\n{}'.format(
                #    path, json.dumps(data, indent=4, sort_keys=True)))
                info = self.prober.get_storage_info(path)
                self._available_disks[path] = Disk.from_info(info)

    def _use_disk(self, disk):
        if disk.path not in self._disks:
            self._disks[disk.path] = disk

    def all_disks(self):
        return [disk for (path, disk) in sorted(self._available_disks.items())]

    def get_disk(self, path):
        return self._available_disks.get(path)

    def add_partition(self, disk, partnum, size, flag=""):
        ## XXX check, round, maybe adjust size?
        self._use_disk(disk)
        if disk._fs is not None:
            raise Exception("%s is already formatted" % (disk.path,))
        p = Partition(device=disk, number=partnum, size=size, flag=flag)
        disk._partitions.append(p)
        self._partitions.append(p)
        return p

    def add_filesystem(self, volume, fstype):
        log.debug("adding %s to %s", fstype, volume)
        if not volume.available:
            raise Exception("%s is not available", volume)
        if isinstance(volume, Disk):
            self._use_disk(volume)
        if volume._fs is not None:
            raise Exception("%s is already formatted")
        volume._fs = fs = Filesystem(volume=volume, fstype=fstype)
        self._filesystems.append(fs)
        return fs

    def add_mount(self, fs, path):
        if fs._mount is not None:
            raise Exception("%s is already mounted")
        fs._mount = m = Mount(device=fs, path=path)
        self._mounts.append(m)
        return m

    def get_mountpoint_to_devpath_mapping(self):
        r = {}
        for m in self._mounts:
            r[m.path] = m.device.volume.path
        return r

    def can_install(self):
        # Do we need to check that there is a disk with the boot flag?
        return '/' in self.get_mountpoint_to_devpath_mapping() and self.bootable()

    def validate_mount(self, mountpoint):
        if mountpoint is None:
            return
        # /usr/include/linux/limits.h:PATH_MAX
        if len(mountpoint) > 4095:
            return 'Path exceeds PATH_MAX'
        mnts = self.get_mountpoint_to_devpath_mapping()
        dev = mnts.get(mountpoint)
        if dev is not None:
            return "%s is already mounted at %s"%(dev, mountpoint)

    def bootable(self):
        ''' true if one disk has a boot partition '''
        for p in self._partitions:
            if p.flag == 'bios_grub':
                return True
        return False
