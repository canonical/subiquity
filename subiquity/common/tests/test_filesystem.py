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

import unittest

from subiquity.common.filesystem import (
    FilesystemManipulator,
    )
from subiquity.models.tests.test_filesystem import (
    make_disk,
    make_model,
    )
from subiquity.models.filesystem import (
    Bootloader,
    DeviceAction,
    )


def make_manipulator(bootloader=None):
    manipulator = FilesystemManipulator()
    manipulator.model = make_model(bootloader)
    manipulator.supports_resilient_boot = True
    return manipulator


def make_manipulator_and_disk(bootloader=None):
    manipulator = make_manipulator(bootloader)
    return manipulator, make_disk(manipulator.model)


class TestFilesystemManipulator(unittest.TestCase):

    def test_delete_encrypted_vg(self):
        manipulator, disk = make_manipulator_and_disk()
        spec = {
            'password': 'passw0rd',
            'devices': {disk},
            'name': 'vg0',
            }
        vg = manipulator.create_volgroup(spec)
        manipulator.delete_volgroup(vg)
        dm_crypts = [
            a for a in manipulator.model._actions if a.type == 'dm_crypt']
        self.assertEqual(dm_crypts, [])

    def test_can_only_add_boot_once(self):
        # This is really testing model code but it's much easier to test with a
        # manipulator around.
        for bl in Bootloader:
            manipulator, disk = make_manipulator_and_disk(bl)
            if DeviceAction.TOGGLE_BOOT not in disk.supported_actions:
                continue
            manipulator.add_boot_disk(disk)
            self.assertFalse(
                disk._can_TOGGLE_BOOT,
                "add_boot_disk(disk) did not make _can_TOGGLE_BOOT false "
                "with bootloader {}".format(bl))

    def assertIsMountedAtBootEFI(self, device):
        efi_mnts = device._m._all(type="mount", path="/boot/efi")
        self.assertEqual(len(efi_mnts), 1)
        self.assertEqual(efi_mnts[0].device.volume, device)

    def assertNotMounted(self, device):
        if device.fs():
            self.assertIs(device.fs().mount(), None)

    def add_existing_boot_partition(self, manipulator, disk):
        if manipulator.model.bootloader == Bootloader.BIOS:
            part = manipulator.model.add_partition(
                disk, size=1 << 20, flag="bios_grub")
        elif manipulator.model.bootloader == Bootloader.UEFI:
            part = manipulator.model.add_partition(
                disk, size=512 << 20, flag="boot")
        elif manipulator.model.bootloader == Bootloader.PREP:
            part = manipulator.model.add_partition(
                disk, size=8 << 20, flag="prep")
        part.preserve = True
        return part

    def assertIsBootDisk(self, manipulator, disk):
        if manipulator.model.bootloader == Bootloader.BIOS:
            self.assertTrue(disk.grub_device)
            self.assertEqual(disk.partitions()[0].flag, "bios_grub")
        elif manipulator.model.bootloader == Bootloader.UEFI:
            for part in disk.partitions():
                if part.flag == "boot" and part.grub_device:
                    return
            self.fail("{} is not a boot disk".format(disk))
        elif manipulator.model.bootloader == Bootloader.PREP:
            for part in disk.partitions():
                if part.flag == "prep" and part.grub_device:
                    self.assertEqual(part.wipe, 'zero')
                    return
            self.fail("{} is not a boot disk".format(disk))

    def assertIsNotBootDisk(self, manipulator, disk):
        if manipulator.model.bootloader == Bootloader.BIOS:
            self.assertFalse(disk.grub_device)
        elif manipulator.model.bootloader == Bootloader.UEFI:
            for part in disk.partitions():
                if part.flag == "boot" and part.grub_device:
                    self.fail("{} is a boot disk".format(disk))
        elif manipulator.model.bootloader == Bootloader.PREP:
            for part in disk.partitions():
                if part.flag == "prep" and part.grub_device:
                    self.fail("{} is a boot disk".format(disk))

    def test_boot_disk_resilient(self):
        for bl in Bootloader:
            if bl == Bootloader.NONE:
                continue
            manipulator = make_manipulator(bl)
            manipulator.supports_resilient_boot = True

            disk1 = make_disk(manipulator.model, preserve=False)
            disk2 = make_disk(manipulator.model, preserve=False)
            disk2p1 = manipulator.model.add_partition(
                disk2, size=disk2.free_for_partitions)

            manipulator.add_boot_disk(disk1)
            self.assertIsBootDisk(manipulator, disk1)
            if bl == Bootloader.UEFI:
                self.assertIsMountedAtBootEFI(disk1.partitions()[0])

            size_before = disk2p1.size
            manipulator.add_boot_disk(disk2)
            self.assertIsBootDisk(manipulator, disk1)
            self.assertIsBootDisk(manipulator, disk2)
            if bl == Bootloader.UEFI:
                self.assertIsMountedAtBootEFI(disk1.partitions()[0])
                self.assertNotMounted(disk2.partitions()[0])
            self.assertEqual(len(disk2.partitions()), 2)
            self.assertEqual(disk2.partitions()[1], disk2p1)
            self.assertEqual(
                disk2.partitions()[0].size + disk2p1.size, size_before)

            manipulator.remove_boot_disk(disk1)
            self.assertIsNotBootDisk(manipulator, disk1)
            self.assertIsBootDisk(manipulator, disk2)
            if bl == Bootloader.UEFI:
                self.assertIsMountedAtBootEFI(disk2.partitions()[0])
            self.assertEqual(len(disk1.partitions()), 0)

            manipulator.remove_boot_disk(disk2)
            self.assertIsNotBootDisk(manipulator, disk2)
            self.assertEqual(len(disk2.partitions()), 1)
            self.assertEqual(disk2p1.size, size_before)

    def test_boot_disk_no_resilient(self):
        for bl in Bootloader:
            if bl == Bootloader.NONE:
                continue
            manipulator = make_manipulator(bl)
            manipulator.supports_resilient_boot = False

            disk1 = make_disk(manipulator.model, preserve=False)
            disk2 = make_disk(manipulator.model, preserve=False)
            disk2p1 = manipulator.model.add_partition(
                disk2, size=disk2.free_for_partitions)

            manipulator.add_boot_disk(disk1)
            self.assertIsBootDisk(manipulator, disk1)
            if bl == Bootloader.UEFI:
                self.assertIsMountedAtBootEFI(disk1.partitions()[0])

            size_before = disk2p1.size
            manipulator.add_boot_disk(disk2)
            self.assertIsNotBootDisk(manipulator, disk1)
            self.assertIsBootDisk(manipulator, disk2)
            if bl == Bootloader.UEFI:
                self.assertIsMountedAtBootEFI(disk2.partitions()[0])
            self.assertEqual(len(disk2.partitions()), 2)
            self.assertEqual(disk2.partitions()[1], disk2p1)
            self.assertEqual(
                disk2.partitions()[0].size + disk2p1.size, size_before)

    def test_boot_disk_existing(self):
        for bl in Bootloader:
            if bl == Bootloader.NONE:
                continue
            manipulator = make_manipulator(bl)

            disk1 = make_disk(manipulator.model, preserve=True)
            part = self.add_existing_boot_partition(manipulator, disk1)

            wipe_before = part.wipe
            manipulator.add_boot_disk(disk1)
            self.assertIsBootDisk(manipulator, disk1)
            if bl == Bootloader.UEFI:
                self.assertIsMountedAtBootEFI(part)

            manipulator.remove_boot_disk(disk1)
            self.assertIsNotBootDisk(manipulator, disk1)
            self.assertEqual(len(disk1.partitions()), 1)
            self.assertEqual(part.wipe, wipe_before)
            if bl == Bootloader.UEFI:
                self.assertNotMounted(part)

    def test_mounting_partition_makes_boot_disk(self):
        manipulator = make_manipulator(Bootloader.UEFI)
        disk1 = make_disk(manipulator.model, preserve=True)
        disk1p1 = manipulator.model.add_partition(
            disk1, size=512 << 20, flag="boot")
        disk1p1.preserve = True
        disk1p2 = manipulator.model.add_partition(
            disk1, size=disk1.free_for_partitions)
        disk1p2.preserve = True
        manipulator.partition_disk_handler(
            disk1, disk1p2, {'fstype': 'ext4', 'mount': '/'})
        efi_mnt = manipulator.model._mount_for_path("/boot/efi")
        self.assertEqual(efi_mnt.device.volume, disk1p1)
