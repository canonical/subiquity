import testtools
import random

from subiquity.models.blockdev import (Blockdev,
                                       blockdev_align_up,
                                       FIRST_PARTITION_OFFSET,
                                       GPT_END_RESERVE)
from subiquity.models.filesystem import FilesystemModel


GB = 1 << 40


class TestBlockdev(testtools.TestCase):
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
        new_size = self.add_partition(partnum=2, partsize=1 * GB, fstype='ext4',
                                      mountpoint='/foo', flag='boot')

        self.assertEqual(len(list(self.bd.partitions)), 2)
        print([action.get() for (num, action) in self.bd.partitions.items()])

        # additional partitions don't have an offset, just alignment
        new_part = self.bd.partitions[2]
        offset_aligned = blockdev_align_up(1 * GB)
        self.assertEqual(offset_aligned, new_part.size)
        self.assertEqual(new_size, new_part.size)
        self.assertEqual(offset_aligned, new_size)

#    def test_blockdev_add_partition_no_format_no_mount(self):
#        pass
