# Copyright 2021 Canonical, Ltd.
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

import unittest

from subiquity.common.filesystem.actions import (
    DeviceAction,
    )
from subiquity.models.filesystem import Bootloader
from subiquity.models.tests.test_filesystem import (
    make_disk,
    make_lv,
    make_model,
    make_model_and_disk,
    make_model_and_lv,
    make_model_and_partition,
    make_model_and_raid,
    make_model_and_vg,
    make_partition,
    make_raid,
    make_vg,
    )


class TestActions(unittest.TestCase):

    def assertActionNotSupported(self, obj, action):
        self.assertNotIn(action, DeviceAction.supported(obj))

    def assertActionPossible(self, obj, action):
        self.assertIn(action, DeviceAction.supported(obj))
        self.assertTrue(action.can(obj)[0])

    def assertActionNotPossible(self, obj, action):
        self.assertIn(action, DeviceAction.supported(obj))
        self.assertFalse(action.can(obj)[0])

    def _test_remove_action(self, model, objects):
        self.assertActionNotPossible(objects[0], DeviceAction.REMOVE)

        vg = model.add_volgroup('vg1', {objects[0], objects[1]})
        self.assertActionPossible(objects[0], DeviceAction.REMOVE)

        # Cannot remove a device from a preexisting VG
        vg.preserve = True
        self.assertActionNotPossible(objects[0], DeviceAction.REMOVE)
        vg.preserve = False

        # Probably this removal should be a model method?
        vg.devices.remove(objects[1])
        objects[1]._constructed_device = None
        self.assertActionNotPossible(objects[0], DeviceAction.REMOVE)
        raid = model.add_raid('md0', 'raid1', set(objects[2:]), set())
        self.assertActionPossible(objects[2], DeviceAction.REMOVE)

        # Cannot remove a device from a preexisting RAID
        raid.preserve = True
        self.assertActionNotPossible(objects[2], DeviceAction.REMOVE)
        raid.preserve = False

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

    def test_disk_action_REFORMAT(self):
        model = make_model()

        disk1 = make_disk(model, preserve=False)
        self.assertActionNotPossible(disk1, DeviceAction.REFORMAT)
        disk1p1 = make_partition(model, disk1, preserve=False)
        self.assertActionPossible(disk1, DeviceAction.REFORMAT)
        model.add_volgroup('vg0', {disk1p1})
        self.assertActionNotPossible(disk1, DeviceAction.REFORMAT)

        disk2 = make_disk(model, preserve=True)
        self.assertActionNotPossible(disk2, DeviceAction.REFORMAT)
        disk2p1 = make_partition(model, disk2, preserve=True)
        self.assertActionPossible(disk2, DeviceAction.REFORMAT)
        model.add_volgroup('vg1', {disk2p1})
        self.assertActionNotPossible(disk2, DeviceAction.REFORMAT)

        disk3 = make_disk(model, preserve=False)
        model.add_volgroup('vg2', {disk3})
        self.assertActionNotPossible(disk3, DeviceAction.REFORMAT)

        disk4 = make_disk(model, preserve=True)
        model.add_volgroup('vg2', {disk4})
        self.assertActionNotPossible(disk4, DeviceAction.REFORMAT)

    def test_disk_action_PARTITION(self):
        model, disk = make_model_and_disk()
        self.assertActionPossible(disk, DeviceAction.PARTITION)
        make_partition(model, disk, size=disk.free_for_partitions//2)
        self.assertActionPossible(disk, DeviceAction.PARTITION)
        make_partition(model, disk, size=disk.free_for_partitions)
        self.assertActionNotPossible(disk, DeviceAction.PARTITION)

        # Can partition a disk with .preserve=True
        disk2 = make_disk(model)
        disk2.preserve = True
        self.assertActionPossible(disk2, DeviceAction.PARTITION)
        # But not if it has a partition.
        make_partition(model, disk2, preserve=True)
        self.assertActionNotPossible(disk2, DeviceAction.PARTITION)

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

    def test_disk_action_TOGGLE_BOOT_NONE(self):
        model, disk = make_model_and_disk(Bootloader.NONE)
        self.assertActionNotSupported(disk, DeviceAction.TOGGLE_BOOT)

    def test_disk_action_TOGGLE_BOOT_BIOS(self):
        model = make_model(Bootloader.BIOS)
        # Disks with msdos partition tables can always be the BIOS boot disk.
        dos_disk = make_disk(model, ptable='msdos', preserve=True)
        self.assertActionPossible(dos_disk, DeviceAction.TOGGLE_BOOT)
        # Even if they have existing partitions
        make_partition(
            model, dos_disk, size=dos_disk.free_for_partitions, preserve=True)
        self.assertActionPossible(dos_disk, DeviceAction.TOGGLE_BOOT)
        # (we never create dos partition tables so no need to test
        # preserve=False case).

        # GPT disks with new partition tables can always be the BIOS boot disk
        gpt_disk = make_disk(model, ptable='gpt', preserve=False)
        self.assertActionPossible(gpt_disk, DeviceAction.TOGGLE_BOOT)
        # Even if they are filled with partitions (we resize partitions to fit)
        make_partition(model, gpt_disk, size=dos_disk.free_for_partitions)
        self.assertActionPossible(gpt_disk, DeviceAction.TOGGLE_BOOT)

        # GPT disks with existing partition tables but no partitions can be the
        # BIOS boot disk (in general we ignore existing empty partition tables)
        gpt_disk2 = make_disk(model, ptable='gpt', preserve=True)
        self.assertActionPossible(gpt_disk2, DeviceAction.TOGGLE_BOOT)
        # If there is an existing *partition* though, it cannot be the boot
        # disk
        make_partition(model, gpt_disk2, preserve=True)
        self.assertActionNotPossible(gpt_disk2, DeviceAction.TOGGLE_BOOT)
        # Unless there is already a bios_grub partition we can reuse
        gpt_disk3 = make_disk(model, ptable='gpt', preserve=True)
        make_partition(
            model, gpt_disk3, flag="bios_grub", preserve=True)
        make_partition(
            model, gpt_disk3, preserve=True)
        self.assertActionPossible(gpt_disk3, DeviceAction.TOGGLE_BOOT)
        # Edge case city: the bios_grub partition has to be first
        gpt_disk4 = make_disk(model, ptable='gpt', preserve=True)
        make_partition(
            model, gpt_disk4, preserve=True)
        make_partition(
            model, gpt_disk4, flag="bios_grub", preserve=True)
        self.assertActionNotPossible(gpt_disk4, DeviceAction.TOGGLE_BOOT)

    def _test_TOGGLE_BOOT_boot_partition(self, bl, flag):
        # The logic for when TOGGLE_BOOT is enabled for both UEFI and PREP
        # bootloaders turns out to be the same, modulo the special flag that
        # has to be present on a partition.
        model = make_model(bl)
        # A disk with a new partition table can always be the UEFI/PREP boot
        # disk.
        new_disk = make_disk(model, preserve=False)
        self.assertActionPossible(new_disk, DeviceAction.TOGGLE_BOOT)
        # Even if they are filled with partitions (we resize partitions to fit)
        make_partition(model, new_disk, size=new_disk.free_for_partitions)
        self.assertActionPossible(new_disk, DeviceAction.TOGGLE_BOOT)

        # A disk with an existing but empty partitions can also be the
        # UEFI/PREP boot disk.
        old_disk = make_disk(model, preserve=True, ptable='gpt')
        self.assertActionPossible(old_disk, DeviceAction.TOGGLE_BOOT)
        # If there is an existing partition though, it cannot.
        make_partition(model, old_disk, preserve=True)
        self.assertActionNotPossible(old_disk, DeviceAction.TOGGLE_BOOT)
        # If there is an existing ESP/PReP partition though, fine!
        make_partition(model, old_disk, flag=flag, preserve=True)
        self.assertActionPossible(old_disk, DeviceAction.TOGGLE_BOOT)

    def test_disk_action_TOGGLE_BOOT_UEFI(self):
        self._test_TOGGLE_BOOT_boot_partition(Bootloader.UEFI, "boot")

    def test_disk_action_TOGGLE_BOOT_PREP(self):
        self._test_TOGGLE_BOOT_boot_partition(Bootloader.PREP, "prep")

    def test_partition_action_INFO(self):
        model, part = make_model_and_partition()
        self.assertActionNotSupported(part, DeviceAction.INFO)

    def test_partition_action_EDIT(self):
        model, part = make_model_and_partition()
        self.assertActionPossible(part, DeviceAction.EDIT)
        model.add_volgroup('vg1', {part})
        self.assertActionNotPossible(part, DeviceAction.EDIT)

    def test_partition_action_REFORMAT(self):
        model, part = make_model_and_partition()
        self.assertActionNotSupported(part, DeviceAction.REFORMAT)

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

        part = make_partition(make_model(Bootloader.BIOS), flag='bios_grub')
        self.assertActionNotPossible(part, DeviceAction.DELETE)
        part = make_partition(make_model(Bootloader.UEFI), flag='boot')
        self.assertActionNotPossible(part, DeviceAction.DELETE)
        part = make_partition(make_model(Bootloader.PREP), flag='prep')
        self.assertActionNotPossible(part, DeviceAction.DELETE)

        # You cannot delete a partition from a disk that has
        # pre-existing partitions (only reformat)
        disk2 = make_disk(model, preserve=True)
        disk2p1 = make_partition(model, disk2, preserve=True)
        self.assertActionNotPossible(disk2p1, DeviceAction.DELETE)

    def test_partition_action_TOGGLE_BOOT(self):
        model, part = make_model_and_partition()
        self.assertActionNotSupported(part, DeviceAction.TOGGLE_BOOT)

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

        raid3 = make_raid(model)
        raid3.preserve = True
        self.assertActionNotPossible(raid3, DeviceAction.EDIT)

    def test_raid_action_REFORMAT(self):
        model = make_model()

        raid1 = make_raid(model)
        self.assertActionNotPossible(raid1, DeviceAction.REFORMAT)
        raid1p1 = make_partition(model, raid1)
        self.assertActionPossible(raid1, DeviceAction.REFORMAT)
        model.add_volgroup('vg0', {raid1p1})
        self.assertActionNotPossible(raid1, DeviceAction.REFORMAT)

        raid2 = make_raid(model)
        raid2.preserve = True
        self.assertActionNotPossible(raid2, DeviceAction.REFORMAT)
        raid2p1 = make_partition(model, raid2, preserve=True)
        self.assertActionPossible(raid2, DeviceAction.REFORMAT)
        model.add_volgroup('vg1', {raid2p1})
        self.assertActionNotPossible(raid2, DeviceAction.REFORMAT)

        raid3 = make_raid(model)
        model.add_volgroup('vg2', {raid3})
        self.assertActionNotPossible(raid3, DeviceAction.REFORMAT)

        raid4 = make_raid(model)
        raid4.preserve = True
        model.add_volgroup('vg2', {raid4})
        self.assertActionNotPossible(raid4, DeviceAction.REFORMAT)

    def test_raid_action_PARTITION(self):
        model, raid = make_model_and_raid()
        self.assertActionPossible(raid, DeviceAction.PARTITION)
        make_partition(model, raid, size=raid.free_for_partitions//2)
        self.assertActionPossible(raid, DeviceAction.PARTITION)
        make_partition(model, raid, size=raid.free_for_partitions)
        self.assertActionNotPossible(raid, DeviceAction.PARTITION)

        # Can partition a raid with .preserve=True
        raid2 = make_raid(model)
        raid2.preserve = True
        self.assertActionPossible(raid2, DeviceAction.PARTITION)
        # But not if it has a partition.
        make_partition(model, raid2, preserve=True)
        self.assertActionNotPossible(raid2, DeviceAction.PARTITION)

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

    def test_raid_action_TOGGLE_BOOT(self):
        model, raid = make_model_and_raid()
        self.assertActionNotSupported(raid, DeviceAction.TOGGLE_BOOT)

    def test_vg_action_INFO(self):
        model, vg = make_model_and_vg()
        self.assertActionNotSupported(vg, DeviceAction.INFO)

    def test_vg_action_EDIT(self):
        model, vg = make_model_and_vg()
        self.assertActionPossible(vg, DeviceAction.EDIT)
        model.add_logical_volume(vg, 'lv1', size=vg.free_for_partitions//2)
        self.assertActionNotPossible(vg, DeviceAction.EDIT)

        vg2 = make_vg(model)
        vg2.preserve = True
        self.assertActionNotPossible(vg2, DeviceAction.EDIT)

    def test_vg_action_REFORMAT(self):
        model, vg = make_model_and_vg()
        self.assertActionNotSupported(vg, DeviceAction.REFORMAT)

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
        vg2 = make_vg(model)
        vg2.preserve = True
        self.assertActionNotPossible(vg2, DeviceAction.CREATE_LV)

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

    def test_vg_action_TOGGLE_BOOT(self):
        model, vg = make_model_and_vg()
        self.assertActionNotSupported(vg, DeviceAction.TOGGLE_BOOT)

    def test_lv_action_INFO(self):
        model, lv = make_model_and_lv()
        self.assertActionNotSupported(lv, DeviceAction.INFO)

    def test_lv_action_EDIT(self):
        model, lv = make_model_and_lv()
        self.assertActionPossible(lv, DeviceAction.EDIT)

    def test_lv_action_REFORMAT(self):
        model, lv = make_model_and_lv()
        self.assertActionNotSupported(lv, DeviceAction.REFORMAT)

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

        lv2 = make_lv(model)
        lv2.preserve = lv2.volgroup.preserve = True
        self.assertActionNotPossible(lv2, DeviceAction.DELETE)

    def test_lv_action_TOGGLE_BOOT(self):
        model, lv = make_model_and_lv()
        self.assertActionNotSupported(lv, DeviceAction.TOGGLE_BOOT)
