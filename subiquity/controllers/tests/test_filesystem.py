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

from subiquitycore.context import Context
from subiquity.controllers.filesystem import (
    FilesystemController,
    )
from subiquity.models.tests.test_filesystem import (
    make_disk,
    make_model,
    )
from subiquity.models.filesystem import (
    Bootloader,
    DeviceAction,
    )


class Thing:
    # Just something to hang attributes off
    pass


class MiniApplication:
    ui = signal = loop = None
    project = "mini"
    autoinstall_config = {}
    answers = {}
    opts = Thing()
    opts.dry_run = True
    opts.bootloader = None
    def report_start_event(*args): pass
    def report_finish_event(*args): pass


def make_controller(bootloader=None):
    app = MiniApplication()
    app.base_model = bm = Thing()
    app.context = Context.new(app)
    bm.target = '/target'
    bm.filesystem = make_model(bootloader)
    controller = FilesystemController(app)
    return controller


def make_controller_and_disk(bootloader=None):
    controller = make_controller(bootloader)
    return controller, make_disk(controller.model)


class TestFilesystemController(unittest.TestCase):

    def test_delete_encrypted_vg(self):
        controller, disk = make_controller_and_disk()
        spec = {
            'password': 'passw0rd',
            'devices': {disk},
            'name': 'vg0',
            }
        vg = controller.create_volgroup(spec)
        controller.delete_volgroup(vg)
        dm_crypts = [
            a for a in controller.model._actions if a.type == 'dm_crypt']
        self.assertEqual(dm_crypts, [])

    def test_can_only_add_boot_once(self):
        # This is really testing model code but it's much easier to test with a
        # controller around.
        for bl in Bootloader:
            controller, disk = make_controller_and_disk(bl)
            if DeviceAction.TOGGLE_BOOT not in disk.supported_actions:
                continue
            controller.add_boot_disk(disk)
            self.assertFalse(
                disk._can_TOGGLE_BOOT,
                "add_boot_disk(disk) did not make _can_TOGGLE_BOOT false "
                "with bootloader {}".format(bl))

    def test_make_boot_disk_BIOS(self):
        controller = make_controller(Bootloader.BIOS)
        disk1 = make_disk(controller.model, preserve=False)

        controller.add_boot_disk(disk1)
        self.assertEqual(len(disk1.partitions()), 1)
        self.assertEqual(disk1.partitions()[0].flag, "bios_grub")
        self.assertTrue(disk1.grub_device)

        controller.remove_boot_disk(disk1)
        self.assertEqual(len(disk1.partitions()), 0)
        self.assertFalse(disk1.grub_device)

        disk2 = make_disk(controller.model, preserve=False)
        disk2p1 = controller.model.add_partition(
            disk2, size=disk2.free_for_partitions)
        size_before = disk2p1.size
        controller.add_boot_disk(disk2)
        self.assertEqual(len(disk2.partitions()), 2)
        self.assertEqual(disk2.partitions()[1], disk2p1)
        self.assertEqual(
            disk2.partitions()[0].size + disk2p1.size, size_before)
        self.assertEqual(disk2.partitions()[0].flag, "bios_grub")
        self.assertTrue(disk2.grub_device)

        controller.remove_boot_disk(disk2)
        self.assertEqual(disk2.partitions(), [disk2p1])
        self.assertEqual(disk2p1.size, size_before)
        self.assertFalse(disk2.grub_device)

    def test_make_boot_disk_BIOS_existing(self):
        controller = make_controller(Bootloader.BIOS)
        disk1 = make_disk(controller.model, preserve=True)
        disk1p1 = controller.model.add_partition(
            disk1, size=1 << 20, flag="bios_grub")
        disk1p1.preserve = True

        self.assertEqual(disk1.partitions(), [disk1p1])
        self.assertFalse(disk1.grub_device)
        controller.add_boot_disk(disk1)
        self.assertEqual(disk1.partitions(), [disk1p1])
        self.assertTrue(disk1.grub_device)
        controller.remove_boot_disk(disk1)
        self.assertEqual(disk1.partitions(), [disk1p1])
        self.assertFalse(disk1.grub_device)

    def assertIsMountedAtBootEFI(self, device):
        efi_mnts = device._m._all(type="mount", path="/boot/efi")
        self.assertEqual(len(efi_mnts), 1)
        self.assertEqual(efi_mnts[0].device.volume, device)

    def assertNotMounted(self, device):
        if device.fs():
            self.assertIs(device.fs().mount(), None)

    def test_make_boot_disk_UEFI(self):
        controller = make_controller(Bootloader.UEFI)
        disk1 = make_disk(controller.model, preserve=False)
        disk2 = make_disk(controller.model, preserve=False)
        disk2p1 = controller.model.add_partition(
            disk2, size=disk2.free_for_partitions)

        controller.add_boot_disk(disk1)
        self.assertEqual(len(disk1.partitions()), 1)
        disk1esp = disk1.partitions()[0]
        self.assertEqual(disk1esp.flag, "boot")
        self.assertEqual(disk1esp.fs().fstype, "fat32")
        self.assertTrue(disk1esp.grub_device)
        self.assertIsMountedAtBootEFI(disk1esp)

        size_before = disk2p1.size
        controller.add_boot_disk(disk2)
        self.assertEqual(len(disk2.partitions()), 2)
        self.assertEqual(disk2.partitions()[1], disk2p1)
        disk2esp = disk2.partitions()[0]
        self.assertEqual(disk2esp.size + disk2p1.size, size_before)
        self.assertEqual(disk2esp.flag, "boot")
        self.assertTrue(disk2esp.grub_device)
        self.assertIsMountedAtBootEFI(disk1esp)
        self.assertNotMounted(disk2esp)

        controller.remove_boot_disk(disk1)
        self.assertIsMountedAtBootEFI(disk2esp)
        self.assertEqual(len(disk1.partitions()), 0)

        controller.remove_boot_disk(disk2)
        self.assertEqual(len(disk2.partitions()), 1)
        self.assertEqual(disk2p1.size, size_before)

    def test_make_boot_disk_UEFI_existing(self):
        controller = make_controller(Bootloader.UEFI)
        disk1 = make_disk(controller.model, preserve=True)
        disk1p1 = controller.model.add_partition(
            disk1, size=512 << 20, flag="boot")
        disk1p1.preserve = True
        disk2 = make_disk(controller.model, preserve=True)

        self.assertEqual(disk1.partitions(), [disk1p1])
        efi_mnt = controller.model._mount_for_path("/boot/efi")
        self.assertEqual(efi_mnt, None)
        controller.add_boot_disk(disk1)
        self.assertEqual(disk1.partitions(), [disk1p1])
        self.assertTrue(disk1p1.grub_device)
        self.assertIsMountedAtBootEFI(disk1p1)
        self.assertEqual(disk1p1.fs().fstype, "fat32")

        controller.add_boot_disk(disk2)
        self.assertEqual(disk1.partitions(), [disk1p1])
        self.assertTrue(disk1p1.grub_device)
        self.assertIsMountedAtBootEFI(disk1p1)

    def test_make_boot_disk_PREP(self):
        controller = make_controller(Bootloader.PREP)
        disk1 = make_disk(controller.model, preserve=False)
        disk2 = make_disk(controller.model, preserve=False)
        disk2p1 = controller.model.add_partition(
            disk2, size=disk2.free_for_partitions)

        controller.add_boot_disk(disk1)
        self.assertEqual(len(disk1.partitions()), 1)
        self.assertEqual(disk1.partitions()[0].flag, "prep")
        self.assertEqual(disk1.partitions()[0].wipe, "zero")
        self.assertTrue(disk1.partitions()[0].grub_device)

        size_before = disk2p1.size
        controller.add_boot_disk(disk2)
        self.assertEqual(len(disk1.partitions()), 0)
        self.assertEqual(len(disk2.partitions()), 2)
        self.assertEqual(disk2.partitions()[1], disk2p1)
        self.assertEqual(
            disk2.partitions()[0].size + disk2p1.size, size_before)
        self.assertEqual(disk2.partitions()[0].flag, "prep")
        self.assertEqual(disk2.partitions()[0].wipe, "zero")

    def test_make_boot_disk_PREP_existing(self):
        controller = make_controller(Bootloader.PREP)
        disk1 = make_disk(controller.model, preserve=True)
        disk1p1 = controller.model.add_partition(
            disk1, size=8 << 20, flag="prep")
        disk1p1.preserve = True

        self.assertEqual(disk1.partitions(), [disk1p1])
        self.assertFalse(disk1p1.grub_device)
        controller.add_boot_disk(disk1)
        self.assertEqual(disk1.partitions(), [disk1p1])
        self.assertTrue(disk1p1.grub_device)
        self.assertEqual(disk1p1.wipe, 'zero')

        controller.remove_boot_disk(disk1)
        self.assertEqual(disk1.partitions(), [disk1p1])
        self.assertFalse(disk1p1.grub_device)
        self.assertEqual(disk1p1.wipe, None)

    def test_mounting_partition_makes_boot_disk(self):
        controller = make_controller(Bootloader.UEFI)
        disk1 = make_disk(controller.model, preserve=True)
        disk1p1 = controller.model.add_partition(
            disk1, size=512 << 20, flag="boot")
        disk1p1.preserve = True
        disk1p2 = controller.model.add_partition(
            disk1, size=disk1.free_for_partitions)
        disk1p2.preserve = True
        controller.partition_disk_handler(
            disk1, disk1p2, {'fstype': 'ext4', 'mount': '/'})
        efi_mnt = controller.model._mount_for_path("/boot/efi")
        self.assertEqual(efi_mnt.device.volume, disk1p1)
