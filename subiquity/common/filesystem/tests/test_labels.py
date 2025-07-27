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

from subiquity.common.filesystem.labels import annotations, for_client, usage_labels
from subiquity.models.tests.test_filesystem import (
    make_dm_crypt,
    make_filesystem,
    make_lv,
    make_model,
    make_model_and_disk,
    make_model_and_partition,
    make_model_and_raid,
    make_mount,
    make_partition,
    make_vg,
    make_zpool,
)


class TestAnnotations(unittest.TestCase):
    def test_disk_annotations(self):
        # disks never have annotations
        model, disk = make_model_and_disk()
        self.assertEqual(annotations(disk), [])
        disk.preserve = True
        self.assertEqual(annotations(disk), [])

    def test_partition_annotations(self):
        model = make_model()
        part = make_partition(model)
        self.assertEqual(annotations(part), ["new"])
        part.preserve = True
        self.assertEqual(annotations(part), ["existing"])

        model = make_model()
        part = make_partition(model, flag="bios_grub")
        self.assertEqual(annotations(part), ["new", "BIOS grub spacer"])
        part.preserve = True
        self.assertEqual(
            annotations(part), ["existing", "unconfigured", "BIOS grub spacer"]
        )
        part.device.grub_device = True
        self.assertEqual(
            annotations(part), ["existing", "configured", "BIOS grub spacer"]
        )

        model = make_model()
        part = make_partition(model, flag="boot", grub_device=True)
        self.assertEqual(annotations(part), ["new", "backup ESP"])
        fs = model.add_filesystem(part, fstype="fat32")
        model.add_mount(fs, "/boot/efi")
        self.assertEqual(annotations(part), ["new", "primary ESP"])

        model = make_model()
        part = make_partition(model, flag="boot", preserve=True)
        self.assertEqual(annotations(part), ["existing", "unused ESP"])
        part.grub_device = True
        self.assertEqual(annotations(part), ["existing", "backup ESP"])
        fs = model.add_filesystem(part, fstype="fat32")
        model.add_mount(fs, "/boot/efi")
        self.assertEqual(annotations(part), ["existing", "primary ESP"])

        model = make_model()
        part = make_partition(model, flag="prep", grub_device=True)
        self.assertEqual(annotations(part), ["new", "PReP"])

        model = make_model()
        part = make_partition(model, flag="prep", preserve=True)
        self.assertEqual(annotations(part), ["existing", "PReP", "unconfigured"])
        part.grub_device = True
        self.assertEqual(annotations(part), ["existing", "PReP", "configured"])

    def test_vg_default_annotations(self):
        model, disk = make_model_and_disk()
        vg = model.add_volgroup("vg-0", {disk})
        self.assertEqual(annotations(vg), ["new"])
        vg.preserve = True
        self.assertEqual(annotations(vg), ["existing"])

    def test_vg_encrypted_annotations(self):
        model, disk = make_model_and_disk()
        dm_crypt = model.add_dm_crypt(disk, key="passw0rd", recovery_key=None)
        vg = model.add_volgroup("vg-0", {dm_crypt})
        self.assertEqual(annotations(vg), ["new", "encrypted"])


class TestUsageLabels(unittest.TestCase):
    def test_partition_usage_labels(self):
        model, partition = make_model_and_partition()
        self.assertEqual(usage_labels(partition), ["unused"])
        fs = model.add_filesystem(partition, "ext4")
        self.assertEqual(
            usage_labels(partition), ["to be formatted as ext4", "not mounted"]
        )
        model._orig_config = model._render_actions()
        fs.preserve = True
        partition.preserve = True
        self.assertEqual(
            usage_labels(partition), ["already formatted as ext4", "not mounted"]
        )
        model.remove_filesystem(fs)
        fs2 = model.add_filesystem(partition, "ext4")
        self.assertEqual(
            usage_labels(partition), ["to be reformatted as ext4", "not mounted"]
        )
        model.add_mount(fs2, "/")
        self.assertEqual(
            usage_labels(partition), ["to be reformatted as ext4", "mounted at /"]
        )


class TestForClient(unittest.TestCase):
    def test_for_client_raid_parts(self):
        model, raid = make_model_and_raid()
        make_partition(model, raid)
        for_client(raid)

    def test_for_client_disk_supported_ptable(self):
        _, disk = make_model_and_disk(ptable="gpt")
        self.assertFalse(for_client(disk).requires_reformat)

    def test_for_client_disk_unsupported_ptable(self):
        _, disk = make_model_and_disk(ptable="unsupported")
        self.assertTrue(for_client(disk).requires_reformat)

    def test_for_client_partition_no_name(self):
        model, disk = make_model_and_disk(ptable="gpt")
        part = make_partition(model, disk, partition_name=None)

        self.assertIsNone(for_client(part).name)

    def test_for_client_partition_with_name(self):
        model, disk = make_model_and_disk(ptable="gpt")
        part = make_partition(model, disk, partition_name="Foobar")

        self.assertEqual("Foobar", for_client(part).name)


class TestEffective(unittest.TestCase):
    def test_part(self):
        model, disk = make_model_and_disk()
        part = make_partition(model, disk)
        fs = make_filesystem(model, part, fstype="fs")
        make_mount(model, fs, "/mount")

        fc = for_client(part)
        self.assertEqual("fs", fc.format)
        self.assertEqual("fs", fc.effective_format)
        self.assertEqual("/mount", fc.mount)
        self.assertEqual("/mount", fc.effective_mount)
        self.assertFalse(fc.effectively_encrypted)

    def test_part_vg_lv(self):
        model, disk = make_model_and_disk()
        part = make_partition(model, disk)
        vg = make_vg(model, pvs=[part])
        lv = make_lv(model, vg)
        fs = make_filesystem(model, lv, fstype="fs")
        make_mount(model, fs, "/mount")

        fc = for_client(part)
        self.assertEqual(None, fc.format)
        self.assertEqual("fs", fc.effective_format)
        self.assertEqual(None, fc.mount)
        self.assertEqual("/mount", fc.effective_mount)
        self.assertFalse(fc.effectively_encrypted)

    def test_part_crypt_vg_lv(self):
        model, disk = make_model_and_disk()
        part = make_partition(model, disk)
        dmc = make_dm_crypt(model, part)
        vg = make_vg(model, pvs=[dmc])
        lv = make_lv(model, vg)
        fs = make_filesystem(model, lv, fstype="fs")
        make_mount(model, fs, "/mount")

        fc = for_client(part)
        self.assertEqual(None, fc.format)
        self.assertEqual("fs", fc.effective_format)
        self.assertEqual(None, fc.mount)
        self.assertEqual("/mount", fc.effective_mount)
        self.assertTrue(fc.effectively_encrypted)

    def test_part_zpool(self):
        model, disk = make_model_and_disk()
        part = make_partition(model, disk)
        make_zpool(model, part, "mypool", "/mount")

        fc = for_client(part)
        self.assertEqual(None, fc.format)
        self.assertEqual("zfs", fc.effective_format)
        self.assertEqual(None, fc.mount)
        self.assertEqual("/mount", fc.effective_mount)
        self.assertFalse(fc.effectively_encrypted)

    def test_part_zpool_keystore(self):
        model, disk = make_model_and_disk()
        part = make_partition(model, disk)
        lk = "luks_keystore"
        make_zpool(model, part, "mypool", "/mount", encryption_style=lk)

        fc = for_client(part)
        self.assertEqual(None, fc.format)
        self.assertEqual("zfs", fc.effective_format)
        self.assertEqual(None, fc.mount)
        self.assertEqual("/mount", fc.effective_mount)
        self.assertTrue(fc.effectively_encrypted)

    def test_part_swap(self):
        model, disk = make_model_and_disk()
        part = make_partition(model, disk)
        make_filesystem(model, part, fstype="swap")

        fc = for_client(part)
        self.assertEqual("swap", fc.format)
        self.assertEqual("swap", fc.effective_format)
        self.assertEqual(None, fc.mount)
        self.assertEqual(None, fc.effective_mount)
        self.assertFalse(fc.effectively_encrypted)

    def test_part_crypt_swap(self):
        model, disk = make_model_and_disk()
        part = make_partition(model, disk)
        dmc = make_dm_crypt(model, part)
        make_filesystem(model, dmc, fstype="swap")

        fc = for_client(part)
        self.assertEqual(None, fc.format)
        self.assertEqual("swap", fc.effective_format)
        self.assertEqual(None, fc.mount)
        self.assertEqual(None, fc.effective_mount)
        self.assertTrue(fc.effectively_encrypted)
