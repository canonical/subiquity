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

import collections
import glob
import logging
import math
import os
import sys

import attr


HUMAN_UNITS = ['B', 'K', 'M', 'G', 'T', 'P']
log = logging.getLogger('subiquity.models.filesystem')


@attr.s(cmp=False)
class FS:
    label = attr.ib()
    is_mounted = attr.ib()


def humanize_size(size):
    if size == 0:
        return "0B"
    p = int(math.floor(math.log(size, 2) / 10))
    # We want to truncate the non-integral part, not round to nearest.
    s = "{:.17f}".format(size / 2**(10*p))
    i = s.index('.')
    s = s[:i+4]
    return s + HUMAN_UNITS[int(p)]


def dehumanize_size(size):
    # convert human 'size' to integer
    size_in = size

    if not size:
        raise ValueError("input cannot be empty")

    if not size[-1].isdigit():
        suffix = size[-1].upper()
        size = size[:-1]
    else:
        suffix = None

    parts = size.split('.')
    if len(parts) > 2:
        raise ValueError(_("{!r} is not valid input").format(size_in))
    elif len(parts) == 2:
        div = 10**len(parts[1])
        size = parts[0] + parts[1]
    else:
        div = 1

    try:
        num = int(size)
    except ValueError:
        raise ValueError(_("{!r} is not valid input").format(size_in))

    if suffix is not None:
        if suffix not in HUMAN_UNITS:
            raise ValueError("unrecognized suffix {!r} in {!r}".format(size_in[-1], size_in))
        mult = 2**(10*HUMAN_UNITS.index(suffix))
    else:
        mult = 1

    if num < 0:
        raise ValueError("{!r}: cannot be negative".format(size_in))

    return num * mult // div


def get_raid_size(level, devices):
    if len(devices) == 0:
        return 0
    min_size = min(dev.size for dev in devices)
    if min_size <= 0:
        return 0
    if level == 0:
        return min_size * len(devices)
    elif level == 1:
        return min_size
    elif level == 5:
        return min_size * (len(devices) - 1)
    elif level == 6:
        return min_size * (len(devices) - 2)
    elif level == 10:
        return min_size * (len(devices) // 2)
    else:
        raise ValueError("unknown raid level %s"%level)


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
            if v is not None:
                r[field.name] = v
    return r

# This code is not going to make much sense unless you have read
# http://curtin.readthedocs.io/en/latest/topics/storage.html. The
# Disk, Partition etc classes correspond to entries in curtin's
# storage config list. They are mostly 'dumb data', all the logic is
# in the FilesystemModel or FilesystemController classes.


@attr.s(cmp=False)
class Disk:

    id = attr.ib(default=id_factory("disk"))
    type = attr.ib(default="disk")
    ptable = attr.ib(default='gpt')
    serial = attr.ib(default=None)
    path = attr.ib(default=None)
    model = attr.ib(default=None)
    wipe = attr.ib(default='superblock')
    preserve = attr.ib(default=False)
    name = attr.ib(default="")
    grub_device = attr.ib(default=False)

    _partitions = attr.ib(default=attr.Factory(list), repr=False) # [Partition]
    _fs = attr.ib(default=None, repr=False) # Filesystem
    _raid = attr.ib(default=None, repr=False) # Raid

    def partitions(self):
        return self._partitions
    def fs(self):
        return self._fs
    def raid(self):
        return self._raid

    def supports_action(self, action):
        if action == "info":
            return True
        if action == "edit":
            return False
        if action == "partition":
            return self.available
        if action == "format":
            return self.empty
        if action == "delete":
            return False

    _info = attr.ib(default=None)

    @classmethod
    def from_info(self, info):
        d = Disk(info=info)
        d.serial = info.serial
        d.path = info.name
        d.model = info.model
        return d

    def info_for_display(self):
        bus = self._info.raw.get('ID_BUS', None)
        major = self._info.raw.get('MAJOR', None)
        if bus is None and major == '253':
            bus = 'virtio'

        devpath = self._info.raw.get('DEVPATH', self.path)
        # XXX probert should be doing this!!
        rotational = '1'
        try:
            dev = os.path.basename(devpath)
            rfile = '/sys/class/block/{}/queue/rotational'.format(dev)
            rotational = open(rfile, 'r').read().strip()
        except (PermissionError, FileNotFoundError, IOError):
            log.exception('WARNING: Failed to read file {}'.format(rfile))
            pass

        dinfo = {
            'bus': bus,
            'devname': self.path,
            'devpath': devpath,
            'model': self.model,
            'serial': self.serial,
            'size': self.size,
            'humansize': humanize_size(self.size),
            'vendor': self._info.vendor,
            'rotational': 'true' if rotational == '1' else 'false',
        }
        if dinfo['serial'] is None:
            dinfo['serial'] = 'unknown'
        if dinfo['model'] is None:
            dinfo['model'] = 'unknown'
        if dinfo['vendor'] is None:
            dinfo['vendor'] = 'unknown'
        return dinfo

    def reset(self):
        self.preserve = False
        self.name = ''
        self.grub_device = ''
        self._partitions = []
        self._fs = None
        self._raid = None

    @property
    def empty(self):
        return self.used == 0

    @property
    def available(self):
        return self.used < self.size

    ok_for_raid = empty

    @property
    def size(self):
        return max(0, align_down(self._info.size) - (2<<20)) # The first and last megabyte of the disk are not usable.

    def desc(self):
        return _("local disk")

    @property
    def label(self):
        if self.serial is not None:
            return self.serial
        return self.path

    @property
    def used(self):
        if self._fs is not None:
            return self.size
        if self._raid is not None:
            return self.size
        r = 0
        for p in self._partitions:
            r += p.size
        return r

    @property
    def free(self):
        return self.size - self.used


@attr.s(cmp=False)
class Partition:

    id = attr.ib(default=id_factory("part"))
    type = attr.ib(default="partition")
    device = attr.ib(default=None) # Disk
    size = attr.ib(default=None)
    wipe = attr.ib(default=None)
    flag = attr.ib(default=None)
    preserve = attr.ib(default=False)

    _fs = attr.ib(default=None, repr=False) # Filesystem
    _raid = attr.ib(default=None, repr=False) # Raid
    def fs(self):
        return self._fs
    def raid(self):
        return self._raid

    def desc(self):
        return _("partition of {}").format(self.device.desc())

    @property
    def label(self):
        return _("partition {} of {}").format(self._number, self.device.label)

    @property
    def ok_for_raid(self):
        if self.flag == 'bios_grub' or self.flag == 'boot':
            return False
        return True

    def supports_action(self, action):
        if action == "info":
            return False
        if action == "edit":
            return True
        if action == "partition":
            return False
        if action == "format":
            return False
        if action == 'delete':
            return self.flag != 'bios_grub' and self.flag != 'boot'

    @property
    def available(self):
        if self.flag == 'bios_grub':
            return False
        if self._fs is None:
            return True
        if self._fs._mount is None:
            fs_obj = FilesystemModel.fs_by_name[self._fs.fstype]
            return fs_obj.is_mounted
        return False

    @property
    def _number(self):
        return self.device._partitions.index(self) + 1

    @property
    def path(self):
        return "%s%s"%(self.device.path, self._number)


@attr.s(cmp=False)
class Raid:
    id = attr.ib(default=id_factory("raid"))
    type = attr.ib(default="raid")
    name = attr.ib(default=None)
    raidlevel = attr.ib(default=None) # 0, 1, 5, 6, 10
    devices = attr.ib(default=attr.Factory(list)) # [Partition or Disk]

    _partitions = attr.ib(default=attr.Factory(list), repr=False) # [Partition]
    _fs = attr.ib(default=None, repr=False) # Filesystem
    _raid = attr.ib(default=None, repr=False) # Filesystem

    def supports_action(self, action):
        if action == "info":
            return False
        if action == "edit":
            return True
        if action == "partition":
            return True
        if action == "format":
            return True
        if action == 'delete':
            return True

    def partitions(self):
        return self._partitions
    def fs(self):
        return self._fs
    def raid(self):
        return self._raid

    @property
    def available(self):
        return self.used < self.size

    @property
    def empty(self):
        return self.used == 0

    ok_for_raid = empty

    @property
    def size(self):
        return get_raid_size(self.raidlevel, self.devices)

    @property
    def used(self):
        if self._fs is not None:
            return self.size
        if self._raid is not None:
            return self.size
        r = 0
        for p in self._partitions:
            r += p.size
        return r

    @property
    def free(self):
        return self.size - self.used

    @property
    def label(self):
        return self.name

    def desc(self):
        return _("software RAID {}").format(self.raidlevel)


@attr.s(cmp=False)
class Filesystem:

    id = attr.ib(default=id_factory("fs"))
    type = attr.ib(default="format")
    fstype = attr.ib(default=None)
    volume = attr.ib(default=None) # Partition or Disk or Raid
    label = attr.ib(default=None)
    uuid = attr.ib(default=None)
    preserve = attr.ib(default=False)

    _mount = attr.ib(default=None, repr=False) # Mount
    def mount(self):
        return self._mount


@attr.s(cmp=False)
class Mount:
    id = attr.ib(default=id_factory("mount"))
    type = attr.ib(default="mount")
    device = attr.ib(default=None) # Filesystem
    path = attr.ib(default=None)


def align_up(size, block_size=1 << 20):
    return (size + block_size - 1) & ~(block_size - 1)

def align_down(size, block_size=1 << 20):
    return size & ~(block_size - 1)


class FilesystemModel(object):

    lower_size_limit = 128*(1<<20)

    supported_filesystems = [
        ('ext4', True, FS('ext4', True)),
        ('xfs', True, FS('xfs', True)),
        ('btrfs', True, FS('btrfs', True)),
        ('---', False),
        ('swap', True, FS('swap', False)),
        #('bcache cache', True, FS('bcache cache', False)),
        #('bcache store', True, FS('bcache store', False)),
        ('---', False),
        ('leave unformatted', True, FS(None, False)),
    ]

    fs_by_name = {}
    longest_fs_name = 0
    for t in supported_filesystems:
        if len(t) > 2:
            fs = t[2]
            if fs.label is not None:
                if len(fs.label) > longest_fs_name:
                    longest_fs_name = len(fs.label)
            fs_by_name[fs.label] = fs
    fs_by_name['fat32'] = FS('fat32', True)

    def __init__(self, prober):
        self.prober = prober
        self._available_disks = {} # keyed by path, eg /dev/sda
        self.reset()

    def reset(self):
        self._disks = collections.OrderedDict() # only gets populated when something uses the disk
        self._partitions = []
        self._raids = []
        self._filesystems = []
        self._mounts = []
        for k, d in self._available_disks.items():
            self._available_disks[k].reset()

    def render(self):
        r = []
        for f in self._filesystems:
            if f.fstype == 'swap':
                if isinstance(f.volume, Partition):
                    f.volume.flag = "swap"
                if f.mount() is None:
                    self.add_mount(f, "")
        for d in self._disks.values():
            r.append(asdict(d))
        for p in self._partitions:
            r.append(asdict(p))
        for d in self._raids:
            r.append(asdict(d))
        for f in self._filesystems:
            r.append(asdict(f))
        for m in sorted(self._mounts, key=lambda m:len(m.path)):
            r.append(asdict(m))
        return r

    def _get_system_mounted_disks(self):
        # This assumes a fairly vanilla setup. It won't list as
        # mounted a disk that is only mounted via lvm, for example.
        mounted_devs = []
        with open('/proc/mounts', encoding=sys.getfilesystemencoding()) as pm:
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
        currently_mounted = {}#self._get_system_mounted_disks()
        for path, data in storage.items():
            log.debug("fs probe %s", path)
            if path in currently_mounted:
                continue
            if data['DEVTYPE'] == 'disk' \
              and not data["DEVPATH"].startswith('/devices/virtual') \
              and data["MAJOR"] != "2" \
              and data["MAJOR"] != "11" \
              and data['attrs'].get('ro') != "1":
                #log.debug('disk={}\n{}'.format(
                #    path, json.dumps(data, indent=4, sort_keys=True)))
                info = self.prober.get_storage_info(path)
                self._available_disks[path] = Disk.from_info(info)

    def _use_disk(self, disk):
        if disk.path not in self._disks:
            self._disks[disk.path] = disk

    def all_disks(self):
        return sorted(self._available_disks.values(), key=lambda x:x.label)

    def all_raids(self):
        return self._raids

    def all_devices(self):
        return self.all_disks() + self.all_raids()

    def get_disk(self, path):
        return self._available_disks.get(path)

    def add_partition(self, disk, size, flag=""):
        if size > disk.free:
            raise Exception("%s > %s", size, disk.free)
        real_size = align_up(size)
        log.debug("add_partition: rounded size from %s to %s", size, real_size)
        self._use_disk(disk)
        if disk._fs is not None:
            raise Exception("%s is already formatted" % (disk.path,))
        p = Partition(device=disk, size=real_size, flag=flag)
        disk._partitions.append(p)
        self._partitions.append(p)
        return p

    def add_raid(self, result):
        r = Raid(name=result['name'], raidlevel=result['level'].value, devices=result['devices'])
        for d in result['devices']:
            if isinstance(d, Disk):
                self._use_disk(d)
            d._raid = r
        self._raids.append(r)
        return r

    def add_filesystem(self, volume, fstype):
        log.debug("adding %s to %s", fstype, volume)
        #if not volume.available:
        #    if not (isinstance(volume, Partition) and volume.flag == 'bios_grub' and fstype == 'fat32'):
        #        raise Exception("{} is not available".format(volume))
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
            if isinstance(m.device.volume, Raid):
                r[m.path] = m.device.volume.name
            else:
                r[m.path] = m.device.volume.path
        return r

    def any_configuration_done(self):
        return len(self._disks) > 0

    def can_install(self):
        # Do we need to check that there is a disk with the boot flag?
        return '/' in self.get_mountpoint_to_devpath_mapping() and self.bootable()

    def bootable(self):
        ''' true if one disk has a boot partition '''
        for p in self._partitions:
            if p.flag == 'bios_grub' or p.flag == 'boot':
                return True
        return False

    def add_swapfile(self):
        for m in self._mounts:
            if m.path == '/':
                if m.device.fstype == 'btrfs':
                    return False
        for fs in self._filesystems:
            if fs.fstype == "swap":
                return False
        return True

## class AttrDict(dict):
##     __getattr__ = dict.__getitem__
##     __setattr__ = dict.__setitem__

## class OldFilesystemModel(object):
##     """ Model representing storage options
##     """

##     # TODO: what is "linear" level?
##     raid_levels = [
##         "0",
##         "1",
##         "5",
##         "6",
##         "10",
##     ]

##     def calculate_raid_size(self, raid_level, raid_devices, spare_devices):
##         '''
##             0: array size is the size of the smallest component partition times
##                the number of component partitions
##             1: array size is the size of the smallest component partition
##             5: array size is the size of the smallest component partition times
##                the number of component partitions munus 1
##             6: array size is the size of the smallest component partition times
##                the number of component partitions munus 2
##         '''
##         # https://raid.wiki.kernel.org/ \
##         #       index.php/RAID_superblock_formats#Total_Size_of_superblock
##         # Version-1 superblock format on-disk layout:
##         # Total size of superblock: 256 Bytes plus 2 bytes per device in the
##         # array
##         log.debug('calc_raid_size: level={} rd={} sd={}'.format(raid_level,
##                                                                 raid_devices,
##                                                                 spare_devices))
##         overhead_bytes = 256 + (2 * (len(raid_devices) + len(spare_devices)))
##         log.debug('calc_raid_size: overhead_bytes={}'.format(overhead_bytes))

##         # find the smallest device
##         min_dev_size = min([d.size for d in raid_devices])
##         log.debug('calc_raid_size: min_dev_size={}'.format(min_dev_size))

##         if raid_level == 0:
##             array_size = min_dev_size * len(raid_devices)
##         elif raid_level == 1:
##             array_size = min_dev_size
##         elif raid_level == 5:
##             array_size = min_dev_size * (len(raid_devices) - 1)
##         elif raid_level == 10:
##             array_size = min_dev_size * int((len(raid_devices) /
##                                              len(spare_devices)))
##         total_size = array_size - overhead_bytes
##         log.debug('calc_raid_size: array_size:{} - overhead:{} = {}'.format(
##                   array_size, overhead_bytes, total_size))
##         return total_size

##     def add_raid_device(self, raidspec):
##         # assume raidspec has already been valided in view/controller
##         log.debug('Attempting to create a raid device')
##         '''
##         raidspec = {
##             'devices': ['/dev/sdb     1.819T, HDS5C3020ALA632',
##                         '/dev/sdc     1.819T, 001-9YN164',
##                         '/dev/sdf     1.819T, 001-9YN164',
##                         '/dev/sdg     1.819T, 001-9YN164',
##                         '/dev/sdh     1.819T, HDS5C3020ALA632',
##                         '/dev/sdi     1.819T, 001-9YN164'],
##                         '/dev/sdj     1.819T, Unknown Model'],
##             'raid_level': '0',
##             'hot_spares': '0',
##             'chunk_size': '4K',
##         }
##         could be /dev/sda1, /dev/md0, /dev/bcache1, /dev/vg_foo/foobar2?
##         '''
##         raid_devices = []
##         spare_devices = []
##         all_devices = [r.split() for r in raidspec.get('devices', [])]
##         nr_spares = int(raidspec.get('hot_spares'))

##         # XXX: curtin requires a partition table on the base devices
##         # and then one partition of type raid
##         for (devpath, *_) in all_devices:
##             disk = self.get_disk(devpath)

##             # add or update a partition to be raid type
##             if disk.path != devpath:  # we must have got a partition
##                 raiddev = disk.get_partition(devpath)
##                 raiddev.flags = 'raid'
##             else:
##                 disk.add_partition(1, disk.freespace, None, None, flag='raid')
##                 raiddev = disk

##             if len(raid_devices) + nr_spares < len(all_devices):
##                 raid_devices.append(raiddev)
##             else:
##                 spare_devices.append(raiddev)

##         # auto increment md number based in registered devices
##         raid_shortname = 'md{}'.format(len(self.raid_devices))
##         raid_dev_name = '/dev/' + raid_shortname
##         raid_serial = '{}_serial'.format(raid_dev_name)
##         raid_model = '{}_model'.format(raid_dev_name)
##         raid_parttype = 'gpt'
##         raid_level = int(raidspec.get('raid_level'))
##         raid_size = self.calculate_raid_size(raid_level, raid_devices,
##                                              spare_devices)

##         # create a Raiddev (pass in only the names)
##         raid_parts = []
##         for dev in raid_devices:
##             self.set_holder(dev.devpath, raid_dev_name)
##             self.set_tag(dev.devpath, 'member of MD ' + raid_shortname)
##             for num, action in dev.partitions.items():
##                 raid_parts.append(action.action_id)
##         spare_parts = []
##         for dev in spare_devices:
##             self.set_holder(dev.devpath, raid_dev_name)
##             self.set_tag(dev.devpath, 'member of MD ' + raid_shortname)
##             for num, action in dev.partitions.items():
##                 spare_parts.append(action.action_id)

##         raid_dev = Raiddev(raid_dev_name, raid_serial, raid_model,
##                            raid_parttype, raid_size,
##                            raid_parts,
##                            raid_level,
##                            spare_parts)

##         # add it to the model's info dict
##         raid_dev_info = {
##             'type': 'disk',
##             'name': raid_dev_name,
##             'size': raid_size,
##             'serial': raid_serial,
##             'vendor': 'Linux Software RAID',
##             'model': raid_model,
##             'is_virtual': True,
##             'raw': {
##                 'MAJOR': '9',
##             },
##         }
##         self.info[raid_dev_name] = AttrDict(raid_dev_info)

##         # add it to the model's raid devices
##         self.raid_devices[raid_dev_name] = raid_dev
##         # add it to the model's devices
##         self.add_device(raid_dev_name, raid_dev)

##         log.debug('Successfully added raid_dev: {}'.format(raid_dev))

##     def add_lvm_volgroup(self, lvmspec):
##         log.debug('Attempting to create an LVM volgroup device')
##         '''
##         lvm_volgroup_spec = {
##             'volgroup': 'my_volgroup_name',
##             'devices': ['/dev/sdb     1.819T, HDS5C3020ALA632']
##         }
##         '''
##         lvm_shortname = lvmspec.get('volgroup')
##         lvm_dev_name = '/dev/' + lvm_shortname
##         lvm_serial = '{}_serial'.format(lvm_dev_name)
##         lvm_model = '{}_model'.format(lvm_dev_name)
##         lvm_parttype = 'gpt'
##         lvm_devices = []

##         # extract just the device name for disks in this volgroup
##         all_devices = [r.split() for r in lvmspec.get('devices', [])]

##         # XXX: curtin requires a partition table on the base devices
##         # and then one partition of type lvm
##         for (devpath, *_) in all_devices:
##             disk = self.get_disk(devpath)

##             self.set_holder(devpath, lvm_dev_name)
##             self.set_tag(devpath, 'member of LVM ' + lvm_shortname)

##             # add or update a partition to be raid type
##             if disk.path != devpath:  # we must have got a partition
##                 pv_dev = disk.get_partition(devpath)
##                 pv_dev.flags = 'lvm'
##             else:
##                 disk.add_partition(1, disk.freespace, None, None, flag='lvm')
##                 pv_dev = disk

##             lvm_devices.append(pv_dev)

##         lvm_size = sum([pv.size for pv in lvm_devices])
##         lvm_device_names = [pv.id for pv in lvm_devices]

##         log.debug('lvm_devices: {}'.format(lvm_device_names))
##         lvm_dev = LVMDev(lvm_dev_name, lvm_serial, lvm_model,
##                          lvm_parttype, lvm_size,
##                          lvm_shortname, lvm_device_names)
##         log.debug('{} volgroup: {} devices: {}'.format(lvm_dev.id,
##                                                        lvm_dev.volgroup,
##                                                        lvm_dev.devices))

##         # add it to the model's info dict
##         lvm_dev_info = {
##             'type': 'disk',
##             'name': lvm_dev_name,
##             'size': lvm_size,
##             'serial': lvm_serial,
##             'vendor': 'Linux Volume Group (LVM2)',
##             'model': lvm_model,
##             'is_virtual': True,
##             'raw': {
##                 'MAJOR': '9',
##             },
##         }
##         self.info[lvm_dev_name] = AttrDict(lvm_dev_info)

##         # add it to the model's lvm devices
##         self.lvm_devices[lvm_dev_name] = lvm_dev
##         # add it to the model's devices
##         self.add_device(lvm_dev_name, lvm_dev)

##         log.debug('Successfully added lvm_dev: {}'.format(lvm_dev))

##     def add_bcache_device(self, bcachespec):
##         # assume bcachespec has already been valided in view/controller
##         log.debug('Attempting to create a bcache device')
##         '''
##         bcachespec = {
##             'backing_device': '/dev/sdc     1.819T, 001-9YN164',
##             'cache_device': '/dev/sdb     1.819T, HDS5C3020ALA632',
##         }
##         could be /dev/sda1, /dev/md0, /dev/vg_foo/foobar2?
##         '''
##         backing_device = self.get_disk(bcachespec['backing_device'].split()[0])
##         cache_device = self.get_disk(bcachespec['cache_device'].split()[0])

##         # auto increment md number based in registered devices
##         bcache_shortname = 'bcache{}'.format(len(self.bcache_devices))
##         bcache_dev_name = '/dev/' + bcache_shortname
##         bcache_serial = '{}_serial'.format(bcache_dev_name)
##         bcache_model = '{}_model'.format(bcache_dev_name)
##         bcache_parttype = 'gpt'
##         bcache_size = backing_device.size

##         # create a Bcachedev (pass in only the names)
##         bcache_dev = Bcachedev(bcache_dev_name, bcache_serial, bcache_model,
##                                bcache_parttype, bcache_size,
##                                backing_device, cache_device)

##         # mark bcache holders
##         self.set_holder(backing_device.devpath, bcache_dev_name)
##         self.set_holder(cache_device.devpath, bcache_dev_name)

##         # tag device use
##         self.set_tag(backing_device.devpath,
##                      'backing store for ' + bcache_shortname)
##         cache_tag = self.get_tag(cache_device.devpath)
##         if len(cache_tag) > 0:
##             cache_tag += ", " + bcache_shortname
##         else:
##             cache_tag = "cache for " + bcache_shortname
##         self.set_tag(cache_device.devpath, cache_tag)

##         # add it to the model's info dict
##         bcache_dev_info = {
##             'type': 'disk',
##             'name': bcache_dev_name,
##             'size': bcache_size,
##             'serial': bcache_serial,
##             'vendor': 'Linux bcache',
##             'model': bcache_model,
##             'is_virtual': True,
##             'raw': {
##                 'MAJOR': '9',
##             },
##         }
##         self.info[bcache_dev_name] = AttrDict(bcache_dev_info)

##         # add it to the model's bcache devices
##         self.bcache_devices[bcache_dev_name] = bcache_dev
##         # add it to the model's devices
##         self.add_device(bcache_dev_name, bcache_dev)

##         log.debug('Successfully added bcache_dev: {}'.format(bcache_dev))

##     def get_bcache_cachedevs(self):
##         ''' return uniq list of bcache cache devices '''
##         cachedevs = list(set([bcache_dev.cache_device for bcache_dev in
##                               self.bcache_devices.values()]))
##         log.debug('bcache cache devs: {}'.format(cachedevs))
##         return cachedevs


##     def set_holder(self, held_device, holder_devpath):
##         ''' insert a hold on `held_device' by adding `holder_devpath' to
##             a list at self.holders[`held_device']
##         '''
##         if held_device not in self.holders:
##             self.holders[held_device] = [holder_devpath]
##         else:
##             self.holders[held_device].append(holder_devpath)

##     def clear_holder(self, held_device, holder_devpath):
##         if held_device in self.holders:
##             self.holders[held_device].remove(holder_devpath)

##     def get_holders(self, held_device):
##         return self.holders.get(held_device, [])

##     def set_tag(self, device, tag):
##         self.tags[device] = tag

##     def get_tag(self, device):
##         return self.tags.get(device, '')
