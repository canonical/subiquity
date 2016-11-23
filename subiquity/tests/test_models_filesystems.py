import random
import yaml

from subiquity.models.blockdev import (Blockdev,
                                       blockdev_align_up,
                                       FIRST_PARTITION_OFFSET,
                                       GPT_END_RESERVE,
                                       sort_actions)
from subiquity.models.filesystem import FilesystemModel
from subiquitycore.tests.utils import TestCase


GB = 1 << 40

class TestFilesystemModel(TestCase):
    def setUp(self):
        super(TestFilesystemModel, self).setUp()
        self.fsm = FilesystemModel(self.prober, self.opts)

    def test_init(self):
        self.assertNotEqual(self.fsm, None)
        self.assertEqual(self.fsm.info, {})
        self.assertEqual(self.fsm.devices, {})
        self.assertEqual(self.fsm.raid_devices, {})
        self.assertEqual(self.fsm.storage, {})

    def test_get_menu(self):
        self.assertEqual(sorted(self.fsm.get_menu()),
                         sorted(self.fsm.fs_menu))

    def test_probe_storage(self):
        '''sd[b..i]'''
        disks = [d for d in self.storage.keys()
                 if self.storage[d]['DEVTYPE'] == 'disk' and
                    self.storage[d]['MAJOR'] in ['8', '253']]
        self.fsm.probe_storage()
        self.assertNotEqual(self.fsm.storage, {})
        self.assertEqual(sorted(self.fsm.info.keys()),
                         sorted(disks))

    def test_get_disk(self):
        self.fsm.probe_storage()
        diskname = random.choice(list(self.fsm.info.keys()))
        disk = Blockdev(diskname,
                        self.fsm.info[diskname].serial,
                        self.fsm.info[diskname].model,
                        size=self.fsm.info[diskname].size)

        test_disk = self.fsm.get_disk(diskname)
        print(disk)
        print(test_disk)
        self.assertEqual(test_disk, disk)

    def test_get_disk_from_partition(self):
        self.fsm.probe_storage()
        diskname = random.choice(list(self.fsm.info.keys()))
        disk = self.fsm.get_disk(diskname)
        disk.add_partition(1, disk.freespace, None, None, flag='raid')

        partpath = '{}{}'.format(disk.path, 1)
        print(partpath)
        self.assertTrue(partpath[-1], 1)
        test_disk = self.fsm.get_disk(partpath)
        print(disk)
        print(test_disk)
        self.assertEqual(test_disk, disk)

    def test_get_all_disks(self):
        self.fsm.probe_storage()
        all_disks = self.fsm.get_all_disks()
        for disk in all_disks:
            self.assertTrue(disk in self.fsm.devices.values())

    def test_get_available_disks(self):
        ''' occupy one of the probed disks and ensure
            that it's not included in the available disks
            result since it's not actually avaialable
        '''
        self.fsm.probe_storage()
        diskname = random.choice(list(self.fsm.info.keys()))
        disk = self.fsm.get_disk(diskname)
        disk.add_partition(1, disk.freespace, None, None, flag='raid')

        avail_disks = self.fsm.get_available_disks()
        self.assertLess(len(avail_disks), len(self.fsm.devices.values()))
        self.assertTrue(disk not in avail_disks)

    def test_add_device(self):
        self.fsm.probe_storage()
        diskname = random.choice(list(self.fsm.info.keys()))
        disk = Blockdev(diskname,
                        self.fsm.info[diskname].serial,
                        self.fsm.info[diskname].model,
                        size=self.fsm.info[diskname].size)

        devname = '/dev/md0'
        self.fsm.add_device(devname, disk)
        self.assertTrue(devname in self.fsm.devices)

    def test_get_partitions(self):
        self.fsm.probe_storage()

        # no partitions
        partitions = self.fsm.get_partitions()
        self.assertEqual(len(partitions), 0)

        # add one to a random disk
        diskname = random.choice(list(self.fsm.info.keys()))
        disk = self.fsm.get_disk(diskname)
        disk.add_partition(1, disk.freespace, None, None, flag='raid')

        # we added one, we should get one
        partitions = self.fsm.get_partitions()
        self.assertEqual(len(partitions), 1)

        # it should have the same base device name
        print(partitions, diskname)
        self.assertTrue(partitions[0].startswith(diskname))

    def test_installable(self):
        self.fsm.probe_storage()
        self.assertEqual(self.fsm.installable(), False)

        # create a partition that installs to root(/)
        diskname = random.choice(list(self.fsm.info.keys()))
        disk = self.fsm.get_disk(diskname)
        disk.add_partition(1, disk.freespace, 'ext4', '/', flag='bios_grub')

        # now we should be installable
        self.assertEqual(self.fsm.installable(), True)

    def test_not_installable(self):
        self.fsm.probe_storage()

        # create a partition that installs to not root(/)
        diskname = random.choice(list(self.fsm.info.keys()))
        disk = self.fsm.get_disk(diskname)
        disk.add_partition(1, disk.freespace, 'ext4', '/opt', flag='bios_grub')

        # we should not be installable
        self.assertEqual(self.fsm.installable(), False)

    def test_bootable(self):
        self.fsm.probe_storage()
        self.assertEqual(self.fsm.bootable(), False)

        # create a partition that installs to root(/)
        diskname = random.choice(list(self.fsm.info.keys()))
        disk = self.fsm.get_disk(diskname)
        disk.add_partition(1, disk.freespace, 'ext4', '/', flag='bios_grub')

        # now we should be installable
        self.assertEqual(self.fsm.bootable(), True)

    def test_get_empty_disks(self):
        self.fsm.probe_storage()

        empty = self.fsm.get_empty_disks()
        avail_disks = self.fsm.get_available_disks()
        self.assertEqual(len(empty), len(avail_disks))

         # create a partition but not FS or Mount
        diskname = random.choice(self.fsm.get_available_disk_names())
        disk = self.fsm.get_disk(diskname)
        disk.add_partition(1, int(disk.freespace / 2), None, None, flag='raid')
        self.assertEqual(len(disk.partitions), 1)
        print('disk: {}'.format(disk))
        print('disk avail: {} is_mounted={} percent_free={}'.format(
                        disk.devpath, disk.is_mounted(), disk.percent_free,
                        len(disk.partitions)))

        # we should have one less empty disk than available
        empty = self.fsm.get_empty_disks()
        avail_disks = self.fsm.get_available_disks()
        print('empty')
        for d in empty:
            print('empty: {} is_mounted={} percent_free={}'.format(
                        d.devpath, d.is_mounted(), d.percent_free,
                        len(d.partitions)))
        print('avail')
        for d in avail_disks:
            print('avail: {} is_mounted={} percent_free={}'.format(
                        d.devpath, d.is_mounted(), d.percent_free,
                        len(d.partitions)))
        self.assertLess(len(empty), len(avail_disks))

    def test_get_empty_disks_names(self):
        self.fsm.probe_storage()
        empty_names = self.fsm.get_empty_disk_names()
        for name in empty_names:
            print(name)
            self.assertTrue(name in self.fsm.devices)

    def test_get_empty_partition_names(self):
        self.fsm.probe_storage()

        empty = self.fsm.get_empty_partition_names()
        self.assertEqual(empty, [])

         # create a partition (not full sized) but not FS or Mount
        diskname = random.choice(self.fsm.get_available_disk_names())
        disk = self.fsm.get_disk(diskname)
        disk.add_partition(1, int(disk.freespace / 2), None, None, flag=None)

        # one empty partition
        [empty] = self.fsm.get_empty_partition_names()

        print('empty={}'.format(empty))
        print('diskane={}'.format(diskname))
        self.assertTrue(diskname in empty)

    def test_get_empty_partition_names(self):
        self.fsm.probe_storage()
        diskname = random.choice(self.fsm.get_available_disk_names())
        disk = self.fsm.get_disk(diskname)
        # create a partition (not full sized) but not FS or Mount
        disk.add_partition(1, int(disk.freespace / 2), None, None, flag='raid')

        avail_disk_names = self.fsm.get_available_disk_names()
        print(disk.devpath)
        print(avail_disk_names)
        self.assertTrue(disk.devpath in avail_disk_names)


class TestBlockdev(TestCase):
    def setUp(self):
        super(TestBlockdev, self).setUp()
        self.devpath = '/dev/foobar'
        self.serial = 'serial'
        self.model = 'model'
        self.parttype = 'gpt'
        self.size = 128 * GB
        self.bd = Blockdev(self.devpath, self.serial, self.model,
                           self.parttype, self.size)

    def test_blockdev_init(self):
        # verify
        self.assertNotEqual(self.bd, None)
        self.assertEqual(self.bd.available, True)
        self.assertEqual(self.bd.blocktype, 'disk')
        self.assertEqual(self.bd.devpath, self.devpath)
        self.assertEqual(self.bd.freespace, self.size)
        self.assertEqual(self.bd.model, self.model)
        self.assertEqual(self.bd.path, self.devpath)
        self.assertEqual(self.bd.percent_free, 100)
        self.assertEqual(self.bd.size, self.size)
        self.assertEqual(self.bd.usedspace, 0)
        self.assertEqual(list(self.bd.available_partitions), [])
        self.assertEqual(list(self.bd.filesystems), [])
        self.assertEqual(list(self.bd.mounts), [])
        self.assertEqual(list(self.bd.partitions), [])
        self.assertEqual(list(self.bd.partnames), [])

        # requires mock
        #self.assertEqual(self.bd.mounted, [])

    def add_partition(self, partnum=1, partsize=1 * GB, fstype='ext4',
                      mountpoint='/', flag='bios_grub'):
        return self.bd.add_partition(partnum, partsize, fstype,
                                     mountpoint, flag)

    def test_blockdev_add_first_partition(self):
        # add a default partition
        partnum=1
        partsize=1*GB
        partpath='{}{}'.format(self.devpath, 1)
        partsize_aligned = self.add_partition()

        # verify
        self.assertEqual(len(list(self.bd.partitions)), 1)
        new_part = self.bd.partitions[1]

        # first partition has an offset and alignment (1M)
        size_plus_offset_aligned = blockdev_align_up(partsize + FIRST_PARTITION_OFFSET)
        self.assertEqual(new_part.size, size_plus_offset_aligned -
                                        FIRST_PARTITION_OFFSET)

        # partition check
        partpath = "{}{}".format(self.devpath, '1')
        self.assertTrue(partpath in self.bd.partnames)

        # format check
        self.assertTrue(partpath in self.bd.filesystems)

        # mount check
        self.assertTrue(partpath in self.bd._mounts)

    def test_blockdev_add_additional_partition(self):
        self.add_partition()
        partsize = 2 * GB
        new_size = self.add_partition(partnum=2, partsize=partsize, fstype='ext4',
                                      mountpoint='/foo', flag='boot')

        self.assertEqual(len(list(self.bd.partitions)), 2)
        print([action.get() for (num, action) in self.bd.partitions.items()])

        # additional partitions don't have an offset, just alignment
        new_part = self.bd.partitions[2]
        offset_aligned = blockdev_align_up(partsize)
        self.assertEqual(offset_aligned, new_part.size)
        self.assertEqual(new_size, new_part.size)
        self.assertEqual(offset_aligned, new_size)

    def test_blockdev_add_partition_no_format_no_mount(self):
        self.add_partition()
        partnum=2
        new_size = self.add_partition(partnum=partnum, partsize=1 * GB, fstype=None,
                                      mountpoint=None, flag='raid')

        partpath='{}{}'.format(self.devpath, partnum)

        self.assertEqual(len(list(self.bd.partitions)), 2)
        print([action.get() for (num, action) in self.bd.partitions.items()])

        # format check
        self.assertTrue(partpath not in self.bd.filesystems)

        # mount check
        self.assertTrue(partpath not in self.bd._mounts)

    def test_blockdev_lastpartnumber(self):
        self.add_partition()
        self.assertEqual(self.bd.lastpartnumber, 1)

    def test_blockdev_get_partition(self):
        partpath='{}{}'.format(self.devpath, '1')
        self.add_partition()
        new_part = self.bd.partitions[1]
        part2 = self.bd.get_partition(partpath)
        self.assertEqual(new_part, part2)

    def test_blockdev_get_partition_with_string(self):
        ''' attempt to add a partition with number as a string type '''
        partnum = '1'
        self.add_partition(partnum=partnum)

        # format the partpath with devpath and partnum
        partpath='{}{}'.format(self.devpath, partnum)

        # we shouldn't be able to get it via a string index
        self.assertRaises(KeyError, lambda x: self.bd.partitions[x], partnum)

        # check that we did create the partition and store it
        # with an integer as the key in the partitions dictionary
        new_part = self.bd.partitions[int(partnum)]
        part2 = self.bd.get_partition(partpath)
        self.assertEqual(new_part, part2)

    def test_blockdev_get_actions(self):
        self.add_partition()
        actions = self.bd.get_actions()

        # actions: disk, partition, format, mount
        self.assertEqual(len(actions), 4)
        action_types = [a.get('type') for a in actions]
        for a in ['disk', 'partition', 'format', 'mount']:
            self.assertTrue(a in action_types)

    def test_blockdev_sort_actions(self):
        self.add_partition()
        actions = sort_actions(self.bd.get_actions())
        # self.bd has a partition, add_partition method adds a
        # disk action, partition action, a format, and a mount point action.
        # We should have a sorted order of actions  which define disk,
        # partition it, format and then mount confirm this by walking up
        # the order and comparing action type
        for (idx, a) in enumerate(actions):
            print(idx, a)

        order = ['disk', 'partition', 'format', 'mount']
        for (idx, type) in enumerate(order):
            print(idx, type)
            self.assertEqual(order[idx], actions[idx].get('type'))

    def test_blockdev_get_fs_table(self):
        self.add_partition()
        partnum = 1
        partsize = self.bd.partitions[partnum].size

        partpath = '{}{}'.format(self.devpath, partnum)
        mount = self.bd._mounts[partpath]
        fstype = self.bd.filesystems[partpath].fstype

        # test
        fs_table = self.bd.get_fs_table()

        # verify
        self.assertEqual(len(fs_table), len(self.bd.partitions))
        self.assertEqual(mount, fs_table[0][0])
        self.assertEqual(partsize, fs_table[0][1])
        self.assertEqual(fstype, fs_table[0][2])
        self.assertEqual(partpath, fs_table[0][3])

    def test_blockdev_get_fs_table_swap(self):
        self.add_partition()
        partnum=2
        self.add_partition(partnum=partnum, partsize=1 * GB, fstype='swap',
                           mountpoint=None, flag=None)

        partsize = self.bd.partitions[partnum].size

        partpath = '{}{}'.format(self.devpath, partnum)
        fstype = 'swap'
        mount = fstype

        # test
        fs_table = self.bd.get_fs_table()

        # verify
        self.assertEqual(len(fs_table), len(self.bd.partitions))
        self.assertEqual(mount, fs_table[1][0])
        self.assertEqual(partsize, fs_table[1][1])
        self.assertEqual(fstype, fs_table[1][2])
        self.assertEqual(partpath, fs_table[1][3])

    def test_blockdev_available_partitions(self):
        # add a non-empty partition
        self.add_partition()

        # we shouldn't have any empty partitions
        empty = self.bd.available_partitions
        self.assertEqual(empty, [])


        partnum=2
        self.add_partition(partnum=partnum, partsize=1 * GB,
                           fstype='leave unformatted',
                           mountpoint=None, flag=None)

        # we should have one empty partition
        empty = self.bd.available_partitions
        print(empty)
        self.assertEqual(len(empty), 1)
