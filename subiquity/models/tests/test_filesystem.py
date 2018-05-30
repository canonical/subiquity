import argparse
import collections
import copy
import logging
import mock
import os
import random
import yaml
import unittest

from subiquitycore.prober import Prober
from subiquity.models.filesystem import (dehumanize_size,
                                         humanize_size,
                                         _get_system_mounted_disks,
                                         FilesystemModel,
                                         Disk,
                                         Filesystem,
                                         Mount,
                                         Partition)
from subiquity.models.subiquity import setup_yaml
from subiquity.tests import fakes
from subiquity.tests.helpers import CiTestCase, simple_mocked_open

# setup OrderedDict yaml dumping
setup_yaml()

EXPECTED_FSM_RENDERED_CONTENT = """\
storage:
    config:
    -   id: sda
        type: disk
        ptable: gpt
        serial: Crucial_CT120M500SSD3_14350D1E6322
        path: /dev/sda
        model: Crucial_CT120M500SSD3
        wipe: superblock
    -   id: sdb
        type: disk
        ptable: gpt
        serial: Hitachi_HDS5C3020ALA632_152D00539000-0:0
        path: /dev/sdb
        model: HDS5C3020ALA632
        wipe: superblock
    -   id: sda1
        type: partition
        device: sda
        size: 2147483648
        flag: boot
    -   id: sda2
        type: partition
        device: sda
        size: 1073741824
    -   id: sdb1
        type: partition
        device: sdb
        size: 2147483648
        flag: swap
    -   id: sda1-fat32
        type: format
        fstype: fat32
        volume: sda1
    -   id: sda2-ext4
        type: format
        fstype: ext4
        volume: sda2
    -   id: sdb1-swap
        type: format
        fstype: swap
        volume: sdb1
    -   id: sdb1-mnt-swap
        type: mount
        device: sdb1-swap
    -   id: sda2-rootfs
        type: mount
        device: sda2-ext4
        path: /
    -   id: sda1-boot-efi
        type: mount
        device: sda1-fat32
        path: /boot/efi
"""


class TestHumanizeSize(unittest.TestCase):

    basics = [
        ('0B', 0),
        ('1.000M', 2**20),
        ('1.500M', 2**20+2**19),
        ('1.500M', 2**20+2**19),
        ('1023.000M', 1023*2**20),
        ('1.000G', 1024*2**20),
        ]

    def test_basics(self):
        """convert common human values to integer values"""
        for string, integer in self.basics:
            with self.subTest(input=string):
                self.assertEqual(string, humanize_size(integer))


class TestDehumanizeSize(unittest.TestCase):

    basics = [
        ('1', 1),
        ('134', 134),

        ('0.5B', 0),  # Does it make sense to allow this?
        ('1B', 1),

        ('1K', 2**10),
        ('1k', 2**10),
        ('0.5K', 2**9),
        ('2.125K', 2**11 + 2**7),

        ('1M', 2**20),
        ('1m', 2**20),
        ('0.5M', 2**19),
        ('2.125M', 2**21 + 2**17),

        ('1G', 2**30),
        ('1g', 2**30),
        ('0.25G', 2**28),
        ('2.5G', 2**31 + 2**29),

        ('1T', 2**40),
        ('1t', 2**40),
        ('4T', 2**42),
        ('4.125T', 2**42 + 2**37),

        ('1P', 2**50),
        ('1P', 2**50),
        ('0.5P', 2**49),
        ('1.5P', 2**50 + 2**49),
        ]

    def test_basics(self):
        for input, expected_output in self.basics:
            with self.subTest(input=input):
                self.assertEqual(expected_output, dehumanize_size(input))

    errors = [
        ('', "input cannot be empty"),
        ('1u', "unrecognized suffix 'u' in '1u'"),
        ('-1', "'-1': cannot be negative"),
        ('1.1.1', "'1.1.1' is not valid input"),
        ('1rm', "'1rm' is not valid input"),
        ('1e6M', "'1e6M' is not valid input"),
        ]

    def test_errors(self):
        for input, expected_error in self.errors:
            with self.subTest(input=input):
                try:
                    dehumanize_size(input)
                except ValueError as e:
                    actual_error = str(e)
                else:
                    self.fail(
                        "dehumanize_size({!r}) did not error".format(input))
                self.assertEqual(expected_error, actual_error)


MB = 1 << 30
GB = 1 << 40


class TestFilesystemDisk(CiTestCase):
    def setUp(self):
        super(TestFilesystemDisk, self).setUp()
        self.info = argparse.Namespace()
        self.info.serial = 'myserial'
        self.info.name = '/wark/xda'
        self.info.model = 'my-fancy-disk-model1'
        self.info.size = 10 * GB

    def test_disk_partitions(self):
        """verify Disk.partitions contains added partition object"""
        partition = Partition()
        disk = Disk.from_info(self.info)
        disk._partitions.append(partition)
        self.assertEqual(partition, disk.partitions()[0])

    def test_disk_filesystem(self):
        """verify Disk.fs() returns same filesystem set on object"""
        filesystem = Filesystem()
        disk = Disk.from_info(self.info)
        disk._fs = filesystem
        self.assertEqual(filesystem, disk.fs())

    def test_disk_desc(self):
        """verify disk.desc() returns expected string"""
        disk = Disk()
        self.assertEqual('local disk', disk.desc())

    def test_disk_from_info(self):
        """verify Disk.from_info() sets serial, path and model"""
        disk = Disk.from_info(self.info)
        self.assertEqual(self.info.serial, disk.serial)
        self.assertEqual(self.info.name, disk.path)
        self.assertEqual(self.info.model, disk.model)

    def test_disk_label_from_serial(self):
        """check disk.label returns disk serial number"""
        disk = Disk()
        path = '/wark/xda'
        disk.path = path
        serial = 'abcdef-123456'
        disk.serial = serial
        self.assertEqual(serial, disk.label)

    def test_disk_label_fallback_to_path(self):
        """check disk.label returns disk.path if serial is none"""
        disk = Disk()
        path = '/wark/xda'
        disk.path = path
        self.assertEqual(path, disk.label)

    def test_disk_reset(self):
        """verify disk is in original state after call to reset"""
        disk = Disk.from_info(self.info)
        copy_of_disk = copy.deepcopy(disk)
        disk._partitions.append(Partition())
        self.assertNotEqual(copy_of_disk, disk)
        disk.reset()
        self.assertEqual(copy_of_disk, disk)

    def test_disk_available(self):
        """verify disk.available is True when disk.used < disk.size"""
        disk = Disk.from_info(self.info)
        self.assertTrue(disk.available)

    def test_disk_not_available(self):
        """verify disk is is False with disk.used >= disk.size"""
        disk = Disk.from_info(self.info)
        disk._partitions.append(Partition(device=disk, size=disk.size))
        self.assertFalse(disk.available)


class TestFilesystemPartition(CiTestCase):
    def test_partition_filesystem(self):
        """verify partition.fs() returns the filesystem object added"""
        part = Partition()
        fs = Filesystem()
        fs.fstype = 'ext4'
        fs.volume = part
        fs.label = 'cloudimg-rootfs'
        part._fs = fs
        self.assertEqual(fs, part.fs())

    def test_partition_desc(self):
        """verify partition.desc() returns description combined from device"""
        disk = Disk()
        part = Partition()
        part.device = disk
        self.assertEqual('partition of local disk', part.desc())

    def test_partition_available(self):
        """verify by default partitions are available"""
        partition = Partition()
        self.assertTrue(partition.available)

    def test_partition_not_available_bios_grub(self):
        """partition.available is False when partition.flag is bios_grub"""
        partition = Partition()
        partition.flag = "bios_grub"
        self.assertFalse(partition.available)

    def test_partition_not_available_has_fs(self):
        """partition.available is False with partition has a fs association"""
        partition = Partition()
        partition._fs = Filesystem()
        self.assertFalse(partition.available)

    def test_partition_available_delegates_to_fs_mount(self):
        """partition.available delegates to fs._mount"""
        def _fsobjs():
            """ Extract the valid FS entries in
                FilesystemModel.supported_filesystems list """
            return [fstup for fstup in FilesystemModel.supported_filesystems
                    if len(fstup) > 2 and fstup[2].label]

        for (fsname, _disp, fs_obj) in _fsobjs():
            partition = Partition()
            fs = Filesystem()
            fs.fstype = fsname
            partition._fs = fs
            self.assertEqual(fs_obj.is_mounted, partition.available)

    def test_partition_not_available_if_mounted(self):
        """partition.available is False with mounted"""
        partition = Partition()
        partition._fs = Filesystem()
        partition._fs._mount = "Not None"
        self.assertFalse(partition.available)

    def test_partition_number(self):
        """partition.number derived from device partition index"""
        disk = Disk()
        partition = Partition()
        partition.device = disk
        disk._partitions.append(partition)
        self.assertEqual(1, partition._number)

    # FIXME: partition.path does not account for named partition (nvmen0p1)
    def test_partition_path(self):
        """partition.path derived from device path and part index"""
        disk = Disk()
        disk.path = "/wark/xda"
        partition = Partition()
        partition.device = disk
        disk._partitions.append(partition)
        self.assertEqual('/wark/xda1', partition.path)


class TestFilesystemFilesystem(CiTestCase):
    def test_filesystem(self):
        """verify Filesystem.mount() returns specified mount"""
        fs = Filesystem()
        mount = Mount()
        fs._mount = mount
        self.assertEqual(mount, fs.mount())


class TestFilesystemModel(CiTestCase):
    def setUp(self):
        super(TestFilesystemModel, self).setUp()
        # don't show logging messages while testing
        logging.disable(logging.CRITICAL)
        # mocking the reading of the fake data saves on IO
        prober = 'subiquitycore.prober.Prober.'
        self.add_patch(prober + '_load_machine_config', 'm_probe_load')
        self.add_patch(prober + 'get_storage', 'm_probe_storage')
        fsm = 'subiquity.models.filesystem.'
        self.add_patch(fsm + '_get_system_mounted_disks', 'm_sys_mounts')
        self.m_sys_mounts.return_value = []
        self._make_fsm()

    def _make_fsm(self):
        self.m_probe_storage.return_value = fakes.FAKE_MACHINE_STORAGE_DATA
        self.m_probe_load.return_value = fakes.FAKE_MACHINE_JSON_DATA
        self.opts = argparse.Namespace()
        self.opts.machine_config = fakes.FAKE_MACHINE_JSON
        self.opts.dry_run = True
        self.prober = Prober(self.opts)
        self.storage = fakes.FAKE_MACHINE_STORAGE_DATA
        self.fsm = FilesystemModel(self.prober)

    def _get_disk_names(self):
        return [d for d in self.storage.keys()
                if self.storage[d]['DEVTYPE'] == 'disk' and
                not self.storage[d]['DEVPATH'].startswith(
                    '/devices/virtual') and
                self.storage[d]['MAJOR'] not in ['2']]

    def _get_disks(self):
        all_disks = {}
        for disk in self._get_disk_names():
            # print('disk path: %s' % disk)
            info = self.fsm.prober.get_storage_info(disk)
            # print('disk info: %s' % info)
            d = Disk.from_info(info)
            # print('disk obj : %s' % d)
            all_disks[disk] = d
        return all_disks

    def test_init(self):
        """validate inital state of FilesystemModel is empty"""
        self.assertNotEqual(self.fsm, None)
        self.assertEqual({}, self.fsm._available_disks)
        self.assertEqual(0, len(self.fsm._disks))
        self.assertEqual([], self.fsm._filesystems)
        self.assertEqual([], self.fsm._partitions)
        self.assertEqual([], self.fsm._mounts)

    def test_probe(self):
        """probe populates fs model with specific disks"""
        self.m_sys_mounts.return_value = []
        disks = self._get_disk_names()
        self.fsm.probe()
        self.assertNotEqual({}, self.fsm._available_disks)
        for disk in disks:
            self.assertIn(disk, self.fsm._available_disks)

    def test_probe_skips_mounted_disks(self):
        """probe skips disks that are currently mounted"""
        self.m_sys_mounts.return_value = ['/dev/sda']
        self.fsm.probe()
        self.assertNotIn('/dev/sda', self.fsm._available_disks)

    # TODO
    # test_probe_skips_devices_virtual (needs comment in code why)
    # test_probe_skips_major_2
    # test_probe_skips_read_only

    def test_all_disks(self):
        """all_disks returns all disks in _available_disks"""
        disks = sorted(self._get_disks().values(), key=lambda x: x.label)
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        self.assertEqual(disks, all_disks)

    # TODO
    # test_use_disk_throws_exception_on_invalid types
    def test_use_disk_no_dupes(self):
        """validate that _use_disks appends disk to _disks list"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        self.fsm._use_disk(disk)
        self.assertIn(disk.path, self.fsm._disks)
        self.assertEqual(1, len(self.fsm._disks))

    def test_use_disk(self):
        """validate that _use_disks does not add duplicates"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        self.fsm._use_disk(disk)
        self.fsm._use_disk(disk)
        self.assertIn(disk.path, self.fsm._disks)
        self.assertEqual(1, len(self.fsm._disks))

    def test_get_disk(self):
        """get_disk returns Disk object by path"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        test_disk = self.fsm.get_disk(disk.path)
        self.assertIsNotNone(disk)
        self.assertIsNotNone(test_disk)
        self.assertEqual(disk, test_disk)

    def test_get_disk_none_path(self):
        """get_disk returns None for bad path"""
        self.fsm.probe()
        test_disk = self.fsm.get_disk(None)
        self.assertIsNone(test_disk)

    def test_add_partition(self):
        """added partition is the same in fsm as the disk"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        partition = self.fsm.add_partition(disk, disk.free)

        partpath = '{}{}'.format(disk.path, 1)
        self.assertTrue(partpath[-1], 1)
        self.assertIn(partition, disk._partitions)
        self.assertIn(partition, self.fsm._partitions)
        self.assertEqual(partition, disk._partitions[0])
        self.assertEqual(partition, self.fsm._partitions[0])
        self.assertEqual(disk._partitions[0], self.fsm._partitions[0])
        self.assertIn(disk.path, self.fsm._disks)

    def test_add_partition_no_space_exception(self):
        """verify exception raised with partition is too big for disk"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        with self.assertRaises(Exception):
            self.fsm.add_partition(disk, disk.free + 1000)

    # FIXME: can a Disk Object only have one filesystem?
    # FIXME: Disk.fs needs a setter
    def test_add_partition_to_disk_with_existing_fs(self):
        """raises exception if disk already has a filesystem"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        self.fsm.add_partition(disk, 10 * MB)
        disk._fs = "Foobar"
        with self.assertRaises(Exception):
            self.fsm.add_partition(disk, disk.free)

    def test_reset(self):
        """verify reset() restores original state to FilesystemModel"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        partition = self.fsm.add_partition(disk, disk.free)
        fs = self.fsm.add_filesystem(partition, 'ext4')
        self.fsm.add_mount(fs, '/wark/foo')
        self.assertNotEqual(collections.OrderedDict(), self.fsm._disks)
        self.assertNotEqual([], self.fsm._partitions)
        self.assertNotEqual([], self.fsm._filesystems)
        self.assertNotEqual([], self.fsm._mounts)
        self.fsm.reset()
        self.assertEqual(collections.OrderedDict(), self.fsm._disks)
        self.assertEqual([], self.fsm._partitions)
        self.assertEqual([], self.fsm._filesystems)
        self.assertEqual([], self.fsm._mounts)

    def test_add_filesystem(self):
        """verify added filesystem is present in the model list"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        partition = self.fsm.add_partition(disk, 1 * MB)
        fs1 = self.fsm.add_filesystem(partition, 'ext4')
        self.assertEqual(fs1, self.fsm._filesystems[0])

    def test_add_filesystem_to_disk(self):
        """verify adding filesystem to a disk with no partitions"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        fs1 = self.fsm.add_filesystem(disk, 'ext4')
        self.assertEqual(fs1, self.fsm._filesystems[0])

    def test_add_filesystem_raises_exception_if_has_fs(self):
        """verify add_filesystem raises exception when it already has an fs"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        partition = self.fsm.add_partition(disk, size=(1 * MB))
        self.fsm.add_filesystem(partition, 'ext4')
        with self.assertRaises(Exception):
            self.fsm.add_filesystem(partition, 'ext4')

    def test_add_filesystem_raises_exception_on_bios_grub(self):
        """raise exception when attempting to add fs to bios_grub partition"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        partition = self.fsm.add_partition(disk=disk, size=(1 * MB),
                                           flag='bios_grub')
        with self.assertRaises(Exception):
            self.fsm.add_filesystem(partition, 'ext4')

    def test_add_filesystem_raises_exception_on_boot_efi(self):
        """raise exception when attempting to add fs to bios_grub partition"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        partition = self.fsm.add_partition(disk=disk, size=(2 * MB),
                                           flag='boot')
        fs = self.fsm.add_filesystem(partition, 'fat32')
        self.fsm.add_mount(fs, '/boot/efi')
        with self.assertRaises(Exception):
            self.fsm.add_filesystem(partition, 'ext4')

    def test_mount_raise_exception_if_fs_is_mounted(self):
        """verify exception raised when attempting to mount fs thats mounted"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        partition = self.fsm.add_partition(disk=disk, size=(2 * MB),
                                           flag='boot')
        fs = self.fsm.add_filesystem(partition, 'fat32')
        self.fsm.add_mount(fs, '/boot/efi')
        with self.assertRaises(Exception):
            self.fsm.add_mount(fs, '/opt')

    def test_get_mountpoint_to_devpath_mapping(self):
        """verify that mount.path in mapping and value is volume.path"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        partition = self.fsm.add_partition(disk=disk, size=(1 * MB))
        fs = self.fsm.add_filesystem(partition, 'ext4')
        mount = self.fsm.add_mount(fs, '/')
        mapping = self.fsm.get_mountpoint_to_devpath_mapping()
        self.assertIn(mount.path, mapping)
        self.assertEqual(partition.path, mapping[mount.path])

    def test_any_configuration_done(self):
        """any_configuration_done is True with config done, else False"""
        self.fsm.probe()
        self.assertFalse(self.fsm.any_configuration_done())
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        self.fsm.add_partition(disk=disk, size=(1 * MB))
        self.assertTrue(self.fsm.any_configuration_done())

    def test_bootable(self):
        """bootable True only if FSM has partition with boot/bios_grub flag"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        partition1 = self.fsm.add_partition(disk=disk, size=(1 * MB))
        fs1 = self.fsm.add_filesystem(partition1, 'ext4')
        self.fsm.add_mount(fs1, '/boot')

        self.assertFalse(self.fsm.bootable())

        partition2 = self.fsm.add_partition(disk=disk, size=(1 * MB),
                                            flag='boot')
        fs2 = self.fsm.add_filesystem(partition2, 'ext4')
        self.fsm.add_mount(fs2, '/')

        self.assertTrue(self.fsm.bootable())

    def test_can_install(self):
        """can_install True if bootable and / in mountpoint mapping"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        partition1 = self.fsm.add_partition(disk=disk, size=(1 * MB))
        fs1 = self.fsm.add_filesystem(partition1, 'ext4')
        self.fsm.add_mount(fs1, '/')

        self.assertFalse(self.fsm.can_install())

        partition2 = self.fsm.add_partition(disk=disk, size=(1 * MB),
                                            flag='boot')
        fs2 = self.fsm.add_filesystem(partition2, 'ext4')
        self.fsm.add_mount(fs2, '/boot')

        self.assertTrue(self.fsm.can_install())

    def test_add_swap(self):
        """verify add_swapfile returns True when swapfile is needed"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        partition = self.fsm.add_partition(disk=disk, size=(1 * MB))
        fs = self.fsm.add_filesystem(partition, 'ext4')
        self.fsm.add_mount(fs, '/')
        partition2 = self.fsm.add_partition(disk=disk, size=(1 * MB))
        fs2 = self.fsm.add_filesystem(partition2, 'ext4')
        self.fsm.add_mount(fs2, '/home')

        self.assertTrue(self.fsm.add_swapfile())

    def test_add_swap_false_with_btrfs(self):
        """verify add_swapfile returns False when / is btrfs"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        partition = self.fsm.add_partition(disk=disk, size=(1 * MB))
        fs = self.fsm.add_filesystem(partition, 'btrfs')
        self.fsm.add_mount(fs, '/')
        self.assertFalse(self.fsm.add_swapfile())

    def test_add_swap_false_with_swap(self):
        """verify add_swapfile returns False when swap fs is present"""
        self.fsm.probe()
        all_disks = self.fsm.all_disks()
        disk = random.choice(all_disks)
        partition = self.fsm.add_partition(disk=disk, size=(1 * MB))
        self.fsm.add_filesystem(partition, 'swap')

        self.assertFalse(self.fsm.add_swapfile())

    def test_render(self):
        """ Test the FSM rendering by comparing to expected yaml output

        In this unittest, the attr.Factory() ends up generating a new
        id value for each Disk, Partition, Filesystem, and Mount which
        means we don't produce the same output from run-to-run. Here
        we replace the id with stable values based on object properties
        """
        self.fsm.probe()
        all_disks = self.fsm.all_disks()

        # id: sda
        for idx, disk in enumerate(all_disks):
            disk.id = os.path.basename(disk.path)

        # pick two disks
        disk1 = all_disks[0]
        disk2 = all_disks[1]

        bootpart = self.fsm.add_partition(disk=disk1, size=(2 * MB),
                                          flag='boot')
        # id: sda1
        bootpart.id = os.path.basename(bootpart.path)
        bootfs = self.fsm.add_filesystem(bootpart, 'fat32')
        # id: sda1-fat32
        bootfs.id = "%s-%s" % (bootpart.id, bootfs.fstype)
        boot_mount = self.fsm.add_mount(bootfs, '/boot/efi')
        # id: sda1-boot-efi
        boot_mount.id = "%s%s" % (bootpart.id,
                                  boot_mount.path.replace('/', '-'))

        rootpart = self.fsm.add_partition(disk=disk1, size=(1 * MB))
        # id: sda2
        rootpart.id = os.path.basename(rootpart.path)
        rootfs = self.fsm.add_filesystem(rootpart, 'ext4')
        # id: sda2-ext4
        rootfs.id = "%s-%s" % (rootpart.id, rootfs.fstype)
        root_mount = self.fsm.add_mount(rootfs, '/')
        # id: sda2-rootfs
        root_mount.id = "%s-rootfs" % (rootpart.id)

        swappart = self.fsm.add_partition(disk=disk2, size=(2 * MB),
                                          flag='swap')
        # id: sdb1
        swappart.id = os.path.basename(swappart.path)
        swapfs = self.fsm.add_filesystem(swappart, 'swap')
        # id: sdb1-swap
        swapfs.id = "%s-%s" % (swappart.id, swapfs.fstype)
        swap_mount = self.fsm.add_mount(swapfs, "")
        # id: sdb1-mnt-swap
        swap_mount.id = "%s-mnt-swap" % swappart.id

        # make sure this is a valid config
        self.assertTrue(self.fsm.can_install())
        content = yaml.dump({'storage': {'config': self.fsm.render()}},
                            default_flow_style=False, indent=4)
        print(content)
        self.assertEqual(EXPECTED_FSM_RENDERED_CONTENT, content)

    def test_render_ensures_swap_volume_is_mounted(self):
        """render includes swap mont when partition.fs='swap' and nomount"""
        self.fsm.probe()
        sda = self.fsm.all_disks()[0]
        sda.id = os.path.basename(sda.path)
        swappart = self.fsm.add_partition(disk=sda, size=(2 * MB))
        swappart.id = os.path.basename(swappart.path)
        swapfs = self.fsm.add_filesystem(swappart, 'swap')
        swapfs.id = "%s-%s" % (swappart.id, swapfs.fstype)

        config = self.fsm.render()
        for item in config:
            print(item)
        mounts = [entry for entry in config if entry['type'] == 'mount']
        self.assertEqual(1, len(mounts))
        swapmount = mounts[0]
        self.assertEqual(swapfs.id, swapmount['device'])

    def test_render_ensures_swap_partition_wo_flag_has_mount_existing(self):
        """render includes swap mount when partition.fs='swap' and mount"""
        self.fsm.probe()
        sda = self.fsm.all_disks()[0]
        sda.id = os.path.basename(sda.path)
        swappart = self.fsm.add_partition(disk=sda, size=(2 * MB))
        swappart.id = os.path.basename(swappart.path)
        swapfs = self.fsm.add_filesystem(swappart, 'swap')
        swapfs.id = "%s-%s" % (swappart.id, swapfs.fstype)
        self.fsm.add_mount(swapfs, "")

        config = self.fsm.render()
        for item in config:
            print(item)
        mounts = [entry for entry in config if entry['type'] == 'mount']
        self.assertEqual(1, len(mounts))
        swapmount = mounts[0]
        self.assertEqual(swapfs.id, swapmount['device'])

    def test_render_ensures_swap_partition_w_flag_has_mount_nomount(self):
        """render includes swap mount when partition.flag='swap' no mount"""
        self.fsm.probe()
        sda = self.fsm.all_disks()[0]
        sda.id = os.path.basename(sda.path)
        swappart = self.fsm.add_partition(disk=sda, size=(2 * MB),
                                          flag='swap')
        swappart.id = os.path.basename(swappart.path)
        swapfs = self.fsm.add_filesystem(swappart, 'swap')
        swapfs.id = "%s-%s" % (swappart.id, swapfs.fstype)

        config = self.fsm.render()
        for item in config:
            print(item)
        mounts = [entry for entry in config if entry['type'] == 'mount']
        self.assertEqual(1, len(mounts))
        swapmount = mounts[0]
        self.assertEqual(swapfs.id, swapmount['device'])

    def test_render_ensures_swap_partition_w_flag_has_mount_existing(self):
        """render includes swap mount when partition.flag='swap' and mount"""
        self.fsm.probe()
        sda = self.fsm.all_disks()[0]
        sda.id = os.path.basename(sda.path)
        swappart = self.fsm.add_partition(disk=sda, size=(2 * MB),
                                          flag='swap')
        swappart.id = os.path.basename(swappart.path)
        swapfs = self.fsm.add_filesystem(swappart, 'swap')
        swapfs.id = "%s-%s" % (swappart.id, swapfs.fstype)
        self.fsm.add_mount(swapfs, "")

        config = self.fsm.render()
        for item in config:
            print(item)
        mounts = [entry for entry in config if entry['type'] == 'mount']
        self.assertEqual(1, len(mounts))
        swapmount = mounts[0]
        self.assertEqual(swapfs.id, swapmount['device'])

    def test_render_ensures_swap_disk_has_mount_existing(self):
        """"render includes swap mount when disk.fs='swap and mount"""
        self.fsm.probe()
        sda = self.fsm.all_disks()[0]
        sda.id = os.path.basename(sda.path)
        swapfs = self.fsm.add_filesystem(sda, 'swap')
        swapfs.id = "%s-%s" % (sda.id, swapfs.fstype)
        config = self.fsm.render()
        for item in config:
            print(item)
        mounts = [entry for entry in config if entry['type'] == 'mount']
        self.assertEqual(1, len(mounts))
        swapmount = mounts[0]
        self.assertEqual(swapfs.id, swapmount['device'])

    def test_render_ensures_swap_disk_has_mount_nomount(self):
        """render includes swap mount when disk.fs='swap' no mount"""
        self.fsm.probe()
        sda = self.fsm.all_disks()[0]
        sda.id = os.path.basename(sda.path)
        swapfs = self.fsm.add_filesystem(sda, 'swap')
        swapfs.id = "%s-%s" % (sda.id, swapfs.fstype)
        self.fsm.add_mount(swapfs, "")

        config = self.fsm.render()
        for item in config:
            print(item)
        mounts = [entry for entry in config if entry['type'] == 'mount']
        self.assertEqual(1, len(mounts))
        swapmount = mounts[0]
        self.assertEqual(swapfs.id, swapmount['device'])


class TestFilesystemModelGetSysMounts(CiTestCase):
    def setUp(self):
        super(TestFilesystemModelGetSysMounts, self).setUp()
        # don't show logging messages while testing
        logging.disable(logging.CRITICAL)

    @mock.patch('subiquity.models.filesystem.glob')
    @mock.patch('subiquity.models.filesystem.os.path.exists')
    def test_get_system_mounts(self, m_exists, m_glob):
        proc_mounts = """\
/dev/xda2 / ext4 rw,relatime,data=ordered 0 0
none /dev tmpfs rw,relatime,size=492k,mode=755,uid=231072,gid=231072 0 0
/dev/xdb /mnt ext4 rw,relatime,data=ordered 0 1
/dev/xdz7 /wark ext4 rw,relatime,data=ordered 0 1
"""
        print(proc_mounts)
        m_exists.side_effect = [
            False,  # os.path.exists('/sys/block/xda2') (False)
            True,   # os.path.exists('/sys/block/xdb') (True)
            False,  # os.path.exists('/sys/block/xdz7') (False)
        ]
        m_glob.glob.side_effect = [
            ['/sys/block/xda/xda2/partition'],
            ['dummy1', 'dummy2'],
        ]
        with simple_mocked_open(content=proc_mounts):
            mounts = _get_system_mounted_disks()

        self.assertEqual(set(['/dev/xda', '/dev/xdb']), mounts)

    @mock.patch('subiquity.models.filesystem.glob')
    @mock.patch('subiquity.models.filesystem.os.path.exists')
    def test_get_system_mounts_nodevs(self, m_exists, m_glob):
        proc_mounts = """\
lxd/containers/subiquity-dev / zfs rw,relatime,xattr,noacl 0 0
none /dev tmpfs rw,relatime,size=492k,mode=755,uid=231072,gid=231072 0 0
proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0
sysfs /sys sysfs rw,relatime 0 0
udev /dev/fuse devtmpfs rw,nosuid,relatime,nr_inodes=2032480,mode=755 0 0
"""
        print(proc_mounts)
        m_exists.side_effect = []
        m_glob.glob.side_effect = []
        with simple_mocked_open(content=proc_mounts):
            mounts = _get_system_mounted_disks()

        self.assertEqual(set(), mounts)
