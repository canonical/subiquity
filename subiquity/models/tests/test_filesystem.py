# Copyright 2019 Canonical, Ltd.
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

from collections import namedtuple
import unittest

from subiquity.models.filesystem import (
    Bootloader,
    dehumanize_size,
    DeviceAction,
    Disk,
    FilesystemModel,
    humanize_size,
    Partition,
    )


class TestHumanizeSize(unittest.TestCase):

    basics = [
        ('1.000M', 2**20),
        ('1.500M', 2**20+2**19),
        ('1.500M', 2**20+2**19),
        ('1023.000M', 1023*2**20),
        ('1.000G', 1024*2**20),
        ]

    def test_basics(self):
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


FakeStorageInfo = namedtuple(
    'FakeStorageInfo', ['name', 'size', 'free', 'serial', 'model'])
FakeStorageInfo.__new__.__defaults__ = (None,) * len(FakeStorageInfo._fields)


def make_model(bootloader=None):
    model = FilesystemModel()
    if bootloader is not None:
        model.bootloader = bootloader
    return model


def make_disk(model):
    serial = 'serial%s' % len(model._actions)
    model._actions.append(Disk(
        m=model, serial=serial,
        info=FakeStorageInfo(size=100*(2**30))))
    return model._actions[-1]


def make_model_and_disk(bootloader=None):
    model = make_model(bootloader)
    return model, make_disk(model)


def make_partition(model, device=None, *, size=None, flag=""):
    if device is None:
        device = make_disk(model)
    if size is None:
        size = device.free_for_partitions//2
    partition = Partition(m=model, device=device, size=size, flag=flag)
    model._actions.append(partition)
    return partition


def make_model_and_partition(bootloader=None):
    model, disk = make_model_and_disk(bootloader)
    return model, make_partition(model, disk)


def make_raid(model):
    name = 'md%s' % len(model._actions)
    return model.add_raid(
        name, 'raid1', {make_disk(model), make_disk(model)}, set())


def make_model_and_raid(bootloader=None):
    model = make_model(bootloader)
    return model, make_raid(model)


def make_vg(model):
    name = 'vg%s' % len(model._actions)
    return model.add_volgroup(
        name, {make_disk(model)})


def make_model_and_vg(bootloader=None):
    model = make_model(bootloader)
    return model, make_vg(model)


def make_lv(model):
    vg = make_vg(model)
    name = 'lv%s' % len(model._actions)
    return model.add_logical_volume(vg, name, vg.free_for_partitions//2)


def make_model_and_lv(bootloader=None):
    model = make_model(bootloader)
    return model, make_lv(model)


class TestFilesystemModel(unittest.TestCase):

    def test_disk_annotations(self):
        # disks never have annotations
        model, disk = make_model_and_disk()
        self.assertEqual(disk.annotations, [])
        disk.preserve = True
        self.assertEqual(disk.annotations, [])

    def test_partition_annotations(self):
        model, disk = make_model_and_disk()
        part = model.add_partition(disk, size=disk.free_for_partitions)
        self.assertEqual(part.annotations, ['new'])
        part.preserve = True
        self.assertEqual(part.annotations, ['existing'])
        part.flag = "boot"
        self.assertEqual(part.annotations, ['existing', 'ESP'])
        part.flag = "prep"
        self.assertEqual(part.annotations, ['existing', 'PReP'])
        part.flag = "bios_grub"
        self.assertEqual(part.annotations, ['existing', 'bios_grub'])

    def test_vg_default_annotations(self):
        model, disk = make_model_and_disk()
        vg = model.add_volgroup('vg-0', {disk})
        self.assertEqual(vg.annotations, ['new'])
        vg.preserve = True
        self.assertEqual(vg.annotations, ['existing'])

    def test_vg_encrypted_annotations(self):
        model, disk = make_model_and_disk()
        dm_crypt = model.add_dm_crypt(disk, key='passw0rd')
        vg = model.add_volgroup('vg-0', {dm_crypt})
        self.assertEqual(vg.annotations, ['new', 'encrypted'])

    def _test_ok_for_xxx(self, model, make_new_device, attr,
                         test_partitions=True):
        # Newly formatted devs are ok_for_raid
        dev1 = make_new_device()
        self.assertTrue(getattr(dev1, attr))
        # A freshly formatted dev is not ok_for_raid
        dev2 = make_new_device()
        model.add_filesystem(dev2, 'ext4')
        self.assertFalse(getattr(dev2, attr))
        if test_partitions:
            # A device with a partition is not ok_for_raid
            dev3 = make_new_device()
            make_partition(model, dev3)
            self.assertFalse(getattr(dev3, attr))

    def test_disk_ok_for_xxx(self):
        model = make_model()
        self._test_ok_for_xxx(
            model, lambda: make_disk(model), "ok_for_raid")
        self._test_ok_for_xxx(
            model, lambda: make_disk(model), "ok_for_lvm_vg")

    def test_partition_ok_for_xxx(self):
        model = make_model()

        def make_new_device():
            return make_partition(model)
        self._test_ok_for_xxx(model, make_new_device, "ok_for_raid", False)
        self._test_ok_for_xxx(model, make_new_device, "ok_for_lvm_vg", False)
        for flag in 'bios_grub', 'boot', 'prep':
            # Possibly we should change this to only care about the
            # flag that matters to the current bootloader.
            p = make_new_device()
            p.flag = flag
            self.assertFalse(p.ok_for_raid)
            self.assertFalse(p.ok_for_lvm_vg)

    def test_raid_ok_for_xxx(self):
        model = make_model()

        def make_new_device():
            return make_raid(model)
        self._test_ok_for_xxx(model, make_new_device, "ok_for_raid", False)
        self._test_ok_for_xxx(model, make_new_device, "ok_for_lvm_vg", False)

    def test_vg_ok_for_xxx(self):
        model, vg = make_model_and_vg()
        self.assertFalse(vg.ok_for_raid)
        self.assertFalse(vg.ok_for_lvm_vg)

    def test_lv_ok_for_xxx(self):
        model, lv = make_model_and_lv()
        self.assertFalse(lv.ok_for_raid)
        self.assertFalse(lv.ok_for_lvm_vg)

    def test_partition_usage_labels(self):
        model, partition = make_model_and_partition()
        self.assertEqual(partition.usage_labels(), ["unused"])
        fs = model.add_filesystem(partition, 'ext4')
        self.assertEqual(
            partition.usage_labels(), ["formatted as ext4", "not mounted"])
        model.add_mount(fs, '/')
        self.assertEqual(
            partition.usage_labels(), ["formatted as ext4", "mounted at /"])

    def assertActionNotSupported(self, obj, action):
        self.assertNotIn(action, obj.supported_actions)

    def assertActionPossible(self, obj, action):
        self.assertIn(action, obj.supported_actions)
        self.assertTrue(obj.action_possible(action)[0])

    def assertActionNotPossible(self, obj, action):
        self.assertIn(action, obj.supported_actions)
        self.assertFalse(obj.action_possible(action)[0])

    def _test_remove_action(self, model, objects):
        self.assertActionNotPossible(objects[0], DeviceAction.REMOVE)

        vg = model.add_volgroup('vg1', {objects[0], objects[1]})
        self.assertActionPossible(objects[0], DeviceAction.REMOVE)
        # Probably this removal should be a model method?
        vg.devices.remove(objects[1])
        objects[1]._constructed_device = None
        self.assertActionNotPossible(objects[0], DeviceAction.REMOVE)
        raid = model.add_raid('md0', 'raid1', set(objects[2:]), set())
        self.assertActionPossible(objects[2], DeviceAction.REMOVE)
        # Probably this removal should be a model method?
        raid.devices.remove(objects[4])
        objects[4]._constructed_device = None
        self.assertActionNotPossible(objects[2], DeviceAction.REMOVE)

    def test_disk_action_INFO(self):
        model, disk = make_model_and_disk()
        self.assertActionPossible(disk, DeviceAction.INFO)

    def test_disk_action_EDIT(self):
        model, disk = make_model_and_disk()
        self.assertActionNotSupported(disk, DeviceAction.EDIT)

    def test_disk_action_PARTITION(self):
        model, disk = make_model_and_disk()
        self.assertActionPossible(disk, DeviceAction.PARTITION)
        make_partition(model, disk, size=disk.free_for_partitions//2)
        self.assertActionPossible(disk, DeviceAction.PARTITION)
        make_partition(model, disk, size=disk.free_for_partitions)
        self.assertActionNotPossible(disk, DeviceAction.PARTITION)

    def test_disk_action_CREATE_LV(self):
        model, disk = make_model_and_disk()
        self.assertActionNotSupported(disk, DeviceAction.CREATE_LV)

    def test_disk_action_FORMAT(self):
        model, disk = make_model_and_disk()
        self.assertActionPossible(disk, DeviceAction.FORMAT)
        make_partition(model, disk)
        self.assertActionNotPossible(disk, DeviceAction.FORMAT)
        disk2 = make_disk(model)
        model.add_volgroup('vg1', {disk2})
        self.assertActionNotPossible(disk2, DeviceAction.FORMAT)

    def test_disk_action_REMOVE(self):
        model = make_model()
        disks = [make_disk(model) for i in range(5)]
        self._test_remove_action(model, disks)

    def test_disk_action_DELETE(self):
        model, disk = make_model_and_disk()
        self.assertActionNotSupported(disk, DeviceAction.DELETE)

    def test_disk_action_MAKE_BOOT(self):
        for bl in Bootloader:
            model, disk = make_model_and_disk(bl)
            if bl == Bootloader.NONE:
                self.assertActionNotSupported(disk, DeviceAction.MAKE_BOOT)
            else:
                self.assertActionPossible(disk, DeviceAction.MAKE_BOOT)

    def test_partition_action_INFO(self):
        model, part = make_model_and_partition()
        self.assertActionNotSupported(part, DeviceAction.INFO)

    def test_partition_action_EDIT(self):
        model, part = make_model_and_partition()
        self.assertActionPossible(part, DeviceAction.EDIT)
        model.add_volgroup('vg1', {part})
        self.assertActionNotPossible(part, DeviceAction.EDIT)

    def test_partition_action_PARTITION(self):
        model, part = make_model_and_partition()
        self.assertActionNotSupported(part, DeviceAction.PARTITION)

    def test_partition_action_CREATE_LV(self):
        model, part = make_model_and_partition()
        self.assertActionNotSupported(part, DeviceAction.CREATE_LV)

    def test_partition_action_FORMAT(self):
        model, part = make_model_and_partition()
        self.assertActionNotSupported(part, DeviceAction.FORMAT)

    def test_partition_action_REMOVE(self):
        model = make_model()
        parts = []
        for i in range(5):
            parts.append(make_partition(model))
        self._test_remove_action(model, parts)

    def test_partition_action_DELETE(self):
        model = make_model()
        part1 = make_partition(model)
        self.assertActionPossible(part1, DeviceAction.DELETE)
        fs = model.add_filesystem(part1, 'ext4')
        self.assertActionPossible(part1, DeviceAction.DELETE)
        model.add_mount(fs, '/')
        self.assertActionPossible(part1, DeviceAction.DELETE)

        part2 = make_partition(model)
        model.add_volgroup('vg1', {part2})
        self.assertActionNotPossible(part2, DeviceAction.DELETE)

        for flag in 'bios_grub', 'boot', 'prep':
            # Possibly we should change this to only prevent the
            # deletion of a partition with a flag that matters to the
            # current bootloader.
            part = make_partition(model, flag=flag)
            self.assertActionNotPossible(part, DeviceAction.DELETE)

    def test_partition_action_MAKE_BOOT(self):
        model, part = make_model_and_partition()
        self.assertActionNotSupported(part, DeviceAction.MAKE_BOOT)

    def test_raid_action_INFO(self):
        model, raid = make_model_and_raid()
        self.assertActionNotSupported(raid, DeviceAction.INFO)

    def test_raid_action_EDIT(self):
        model = make_model()
        raid1 = make_raid(model)
        self.assertActionPossible(raid1, DeviceAction.EDIT)
        model.add_volgroup('vg1', {raid1})
        self.assertActionNotPossible(raid1, DeviceAction.EDIT)
        raid2 = make_raid(model)
        make_partition(model, raid2)
        self.assertActionNotPossible(raid2, DeviceAction.EDIT)

    def test_raid_action_PARTITION(self):
        model, raid = make_model_and_raid()
        self.assertActionPossible(raid, DeviceAction.PARTITION)
        make_partition(model, raid, size=raid.free_for_partitions//2)
        self.assertActionPossible(raid, DeviceAction.PARTITION)
        make_partition(model, raid, size=raid.free_for_partitions)
        self.assertActionNotPossible(raid, DeviceAction.PARTITION)

    def test_raid_action_CREATE_LV(self):
        model, raid = make_model_and_raid()
        self.assertActionNotSupported(raid, DeviceAction.CREATE_LV)

    def test_raid_action_FORMAT(self):
        model, raid = make_model_and_raid()
        self.assertActionPossible(raid, DeviceAction.FORMAT)
        make_partition(model, raid)
        self.assertActionNotPossible(raid, DeviceAction.FORMAT)
        raid2 = make_raid(model)
        model.add_volgroup('vg1', {raid2})
        self.assertActionNotPossible(raid2, DeviceAction.FORMAT)

    def test_raid_action_REMOVE(self):
        model = make_model()
        raids = [make_raid(model) for i in range(5)]
        self._test_remove_action(model, raids)

    def test_raid_action_DELETE(self):
        model, raid = make_model_and_raid()

        raid1 = make_raid(model)
        self.assertActionPossible(raid1, DeviceAction.DELETE)
        part = make_partition(model, raid1)
        self.assertActionPossible(raid1, DeviceAction.DELETE)
        fs = model.add_filesystem(part, 'ext4')
        self.assertActionPossible(raid1, DeviceAction.DELETE)
        model.add_mount(fs, '/')
        self.assertActionNotPossible(raid1, DeviceAction.DELETE)

        raid2 = make_raid(model)
        self.assertActionPossible(raid2, DeviceAction.DELETE)
        fs = model.add_filesystem(raid2, 'ext4')
        self.assertActionPossible(raid2, DeviceAction.DELETE)
        model.add_mount(fs, '/')
        self.assertActionPossible(raid2, DeviceAction.DELETE)

        raid2 = make_raid(model)
        model.add_volgroup('vg0', {raid2})
        self.assertActionNotPossible(raid2, DeviceAction.DELETE)

    def test_raid_action_MAKE_BOOT(self):
        model, raid = make_model_and_raid()
        self.assertActionNotSupported(raid, DeviceAction.MAKE_BOOT)

    def test_vg_action_INFO(self):
        model, vg = make_model_and_vg()
        self.assertActionNotSupported(vg, DeviceAction.INFO)

    def test_vg_action_EDIT(self):
        model, vg = make_model_and_vg()
        self.assertActionPossible(vg, DeviceAction.EDIT)
        model.add_logical_volume(vg, 'lv1', size=vg.free_for_partitions//2)
        self.assertActionNotPossible(vg, DeviceAction.EDIT)

    def test_vg_action_PARTITION(self):
        model, vg = make_model_and_vg()
        self.assertActionNotSupported(vg, DeviceAction.PARTITION)

    def test_vg_action_CREATE_LV(self):
        model, vg = make_model_and_vg()
        self.assertActionPossible(vg, DeviceAction.CREATE_LV)
        model.add_logical_volume(vg, 'lv1', size=vg.free_for_partitions//2)
        self.assertActionPossible(vg, DeviceAction.CREATE_LV)
        model.add_logical_volume(vg, 'lv2', size=vg.free_for_partitions)
        self.assertActionNotPossible(vg, DeviceAction.CREATE_LV)

    def test_vg_action_FORMAT(self):
        model, vg = make_model_and_vg()
        self.assertActionNotSupported(vg, DeviceAction.FORMAT)

    def test_vg_action_REMOVE(self):
        model, vg = make_model_and_vg()
        self.assertActionNotSupported(vg, DeviceAction.REMOVE)

    def test_vg_action_DELETE(self):
        model, vg = make_model_and_vg()
        self.assertActionPossible(vg, DeviceAction.DELETE)
        self.assertActionPossible(vg, DeviceAction.DELETE)
        lv = model.add_logical_volume(
            vg, 'lv0', size=vg.free_for_partitions//2)
        self.assertActionPossible(vg, DeviceAction.DELETE)
        fs = model.add_filesystem(lv, 'ext4')
        self.assertActionPossible(vg, DeviceAction.DELETE)
        model.add_mount(fs, '/')
        self.assertActionNotPossible(vg, DeviceAction.DELETE)

    def test_vg_action_MAKE_BOOT(self):
        model, vg = make_model_and_vg()
        self.assertActionNotSupported(vg, DeviceAction.MAKE_BOOT)

    def test_lv_action_INFO(self):
        model, lv = make_model_and_lv()
        self.assertActionNotSupported(lv, DeviceAction.INFO)

    def test_lv_action_EDIT(self):
        model, lv = make_model_and_lv()
        self.assertActionPossible(lv, DeviceAction.EDIT)

    def test_lv_action_PARTITION(self):
        model, lv = make_model_and_lv()
        self.assertActionNotSupported(lv, DeviceAction.PARTITION)

    def test_lv_action_CREATE_LV(self):
        model, lv = make_model_and_lv()
        self.assertActionNotSupported(lv, DeviceAction.CREATE_LV)

    def test_lv_action_FORMAT(self):
        model, lv = make_model_and_lv()
        self.assertActionNotSupported(lv, DeviceAction.FORMAT)

    def test_lv_action_REMOVE(self):
        model, lv = make_model_and_lv()
        self.assertActionNotSupported(lv, DeviceAction.REMOVE)

    def test_lv_action_DELETE(self):
        model, lv = make_model_and_lv()
        self.assertActionPossible(lv, DeviceAction.DELETE)
        fs = model.add_filesystem(lv, 'ext4')
        self.assertActionPossible(lv, DeviceAction.DELETE)
        model.add_mount(fs, '/')
        self.assertActionPossible(lv, DeviceAction.DELETE)

    def test_lv_action_MAKE_BOOT(self):
        model, lv = make_model_and_lv()
        self.assertActionNotSupported(lv, DeviceAction.MAKE_BOOT)
