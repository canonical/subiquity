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

import pathlib
import unittest
from typing import Optional
from unittest import mock
from unittest.mock import Mock

import attr
import yaml

from subiquity.common.filesystem import gaps
from subiquity.common.types.storage import RecoveryKey
from subiquity.models.filesystem import (
    LVM_CHUNK_SIZE,
    ZFS,
    ActionRenderMode,
    Bootloader,
    Disk,
    Filesystem,
    FilesystemModel,
    NotFinalPartitionError,
    NVMeController,
    Partition,
    RecoveryKeyHandler,
    ZPool,
    align_down,
    dehumanize_size,
    get_canmount,
    get_raid_size,
    humanize_size,
)
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.parameterized import parameterized
from subiquitycore.utils import matching_dicts


class TestHumanizeSize(unittest.TestCase):
    basics = [
        ("1.000M", 2**20),
        ("1.500M", 2**20 + 2**19),
        ("1.500M", 2**20 + 2**19),
        ("1023.000M", 1023 * 2**20),
        ("1.000G", 1024 * 2**20),
    ]

    def test_basics(self):
        for string, integer in self.basics:
            with self.subTest(input=string):
                self.assertEqual(string, humanize_size(integer))


class TestDehumanizeSize(unittest.TestCase):
    basics = [
        ("1", 1),
        ("134", 134),
        ("0.5B", 0),  # Does it make sense to allow this?
        ("1B", 1),
        ("1K", 2**10),
        ("1k", 2**10),
        ("0.5K", 2**9),
        ("2.125K", 2**11 + 2**7),
        ("1M", 2**20),
        ("1m", 2**20),
        ("0.5M", 2**19),
        ("2.125M", 2**21 + 2**17),
        ("1G", 2**30),
        ("1g", 2**30),
        ("0.25G", 2**28),
        ("2.5G", 2**31 + 2**29),
        ("1T", 2**40),
        ("1t", 2**40),
        ("4T", 2**42),
        ("4.125T", 2**42 + 2**37),
        ("1P", 2**50),
        ("1P", 2**50),
        ("0.5P", 2**49),
        ("1.5P", 2**50 + 2**49),
    ]

    def test_basics(self):
        for input, expected_output in self.basics:
            with self.subTest(input=input):
                self.assertEqual(expected_output, dehumanize_size(input))

    errors = [
        ("", "input cannot be empty"),
        ("1u", "unrecognized suffix 'u' in '1u'"),
        ("-1", "'-1': cannot be negative"),
        ("1.1.1", "'1.1.1' is not valid input"),
        ("1rm", "'1rm' is not valid input"),
        ("1e6M", "'1e6M' is not valid input"),
    ]

    def test_errors(self):
        for input, expected_error in self.errors:
            with self.subTest(input=input):
                try:
                    dehumanize_size(input)
                except ValueError as e:
                    actual_error = str(e)
                else:
                    self.fail("dehumanize_size({!r}) did not error".format(input))
                self.assertEqual(expected_error, actual_error)


@attr.s
class FakeDev:
    size = attr.ib()
    id = attr.ib(default="id")


class TestRoundRaidSize(unittest.TestCase):
    def test_lp1816777(self):
        self.assertLessEqual(
            get_raid_size("raid1", [FakeDev(500107862016)] * 2), 499972571136
        )


@attr.s
class FakeStorageInfo:
    name = attr.ib(default=None)
    size = attr.ib(default=None)
    free = attr.ib(default=None)
    serial = attr.ib(default=None)
    model = attr.ib(default=None)
    raw = attr.ib(default=attr.Factory(dict))


def make_model(bootloader=None, storage_version=None, supports_nvme_tcp_booting=False):
    model = FilesystemModel(
        root="/tmp", opt_supports_nvme_tcp_booting=supports_nvme_tcp_booting
    )
    if bootloader is not None:
        model.bootloader = bootloader
    if storage_version is not None:
        model.storage_version = storage_version
    model._probe_data = {}
    return model


def make_disk(fs_model=None, **kw):
    if fs_model is None:
        fs_model = make_model()
    if "serial" not in kw:
        kw["serial"] = "serial%s" % len(fs_model._actions)
    if "path" not in kw:
        kw["path"] = "/dev/thing%s" % len(fs_model._actions)
    if "ptable" not in kw:
        kw["ptable"] = "gpt"
    size = kw.pop("size", 100 * (2**30))
    fs_model._actions.append(Disk(m=fs_model, info=FakeStorageInfo(size=size), **kw))
    disk = fs_model._actions[-1]
    return disk


def make_model_and_disk(bootloader=None, storage_version=None, **kw):
    model = make_model(bootloader, storage_version)
    return model, make_disk(model, **kw)


def make_partition(
    model=None, device=None, *, preserve=False, size=None, offset=None, **kw
):
    flag = kw.pop("flag", None)
    if device is None:
        device = make_disk(model)
    model = device._m
    if size is None or size == -1 or offset is None:
        if offset is None:
            gap = gaps.largest_gap(device)
            offset = gap.offset
        else:
            gap = gaps.includes(device, offset)
        if size is None:
            size = gap.size // 2
        elif size == -1:
            size = gap.size - (offset - gap.offset)
    partition = Partition(
        m=model,
        device=device,
        size=size,
        offset=offset,
        preserve=preserve,
        flag=flag,
        **kw,
    )
    if partition.preserve:
        partition._info = FakeStorageInfo(size=size)
    model._actions.append(partition)
    return partition


def make_filesystem(model, partition, *, fstype="ext4", **kw):
    return Filesystem(m=model, volume=partition, fstype=fstype, **kw)


def make_model_and_partition(bootloader=None):
    model, disk = make_model_and_disk(bootloader)
    return model, make_partition(model, disk)


def make_raid(model, disks=None, **kw):
    name = "md%s" % len(model._actions)
    if disks is None:
        disks = {make_disk(model), make_disk(model)}
    r = model.add_raid(name, "raid1", disks, set())
    size = r.size
    for k, v in kw.items():
        setattr(r, k, v)
    if r.preserve:
        r._info = FakeStorageInfo(size=size)
    return r


def make_model_and_raid(bootloader=None):
    model = make_model(bootloader)
    return model, make_raid(model)


def make_vg(model, pvs=None):
    name = "vg%s" % len(model._actions)

    if pvs is None:
        pvs = [make_disk(model)]

    return model.add_volgroup(name, pvs)


def make_model_and_vg(bootloader=None):
    model = make_model(bootloader)
    return model, make_vg(model)


def make_lv(model, vg=None, size=None):
    if vg is None:
        vg = make_vg(model)
    name = "lv%s" % len(model._actions)
    size = gaps.largest_gap_size(vg) if size is None else size
    return model.add_logical_volume(vg, name, size)


def make_model_and_lv(bootloader=None, lv_size=None):
    model = make_model(bootloader)
    return model, make_lv(model, size=lv_size)


def make_zpool(model=None, device=None, pool=None, mountpoint=None, **kw):
    if model is None:
        model = make_model()
    if device is None:
        device = make_disk(model)
    if pool is None:
        pool = f"pool{len(model._actions)}"
    return model.add_zpool(device=device, pool=pool, mountpoint=mountpoint, **kw)


def make_zfs(model, *, pool, **kw):
    zfs = ZFS(m=model, pool=pool, **kw)
    model._actions.append(zfs)
    return zfs


def make_nvme_controller(
    model,
    *,
    transport: str,
    tcp_addr: Optional[str] = None,
    tcp_port: Optional[str] = None,
) -> NVMeController:
    ctrler = NVMeController(
        m=model, transport=transport, tcp_addr=tcp_addr, tcp_port=tcp_port
    )
    model._actions.append(ctrler)
    return ctrler


class TestFilesystemModel(unittest.TestCase):
    def _test_ok_for_xxx(self, model, make_new_device, attr, test_partitions=True):
        # Newly formatted devs are ok_for_raid
        dev1 = make_new_device(model)
        self.assertTrue(getattr(dev1, attr))
        # A freshly formatted dev is not ok_for_raid
        dev2 = make_new_device(model)
        model.add_filesystem(dev2, "ext4")
        self.assertFalse(getattr(dev2, attr))
        if test_partitions:
            # A device with a partition is not ok_for_raid
            dev3 = make_new_device(model)
            make_partition(model, dev3)
            self.assertFalse(getattr(dev3, attr))
        # Empty existing devices are ok
        dev4 = make_new_device(model, preserve=True)
        self.assertTrue(getattr(dev4, attr))
        # A dev with an existing filesystem is ok (there is no
        # way to remove the format)
        dev5 = make_new_device(model, preserve=True)
        fs = model.add_filesystem(dev5, "ext4")
        fs.preserve = True
        self.assertTrue(dev5.ok_for_raid)
        # But a existing, *mounted* filesystem is not.
        model.add_mount(fs, "/")
        self.assertFalse(dev5.ok_for_raid)

    def test_disk_ok_for_xxx(self):
        model = make_model()

        self._test_ok_for_xxx(model, make_disk, "ok_for_raid")
        self._test_ok_for_xxx(model, make_disk, "ok_for_lvm_vg")

    def test_partition_ok_for_xxx(self):
        model = make_model()

        self._test_ok_for_xxx(model, make_partition, "ok_for_raid", False)
        self._test_ok_for_xxx(model, make_partition, "ok_for_lvm_vg", False)

        part = make_partition(make_model(Bootloader.BIOS), flag="bios_grub")
        self.assertFalse(part.ok_for_raid)
        self.assertFalse(part.ok_for_lvm_vg)
        part = make_partition(make_model(Bootloader.UEFI), flag="boot")
        self.assertFalse(part.ok_for_raid)
        self.assertFalse(part.ok_for_lvm_vg)
        part = make_partition(make_model(Bootloader.PREP), flag="prep")
        self.assertFalse(part.ok_for_raid)
        self.assertFalse(part.ok_for_lvm_vg)

    def test_raid_ok_for_xxx(self):
        model = make_model()

        self._test_ok_for_xxx(model, make_raid, "ok_for_raid", False)
        self._test_ok_for_xxx(model, make_raid, "ok_for_lvm_vg", False)

    def test_vg_ok_for_xxx(self):
        model, vg = make_model_and_vg()
        self.assertFalse(vg.ok_for_raid)
        self.assertFalse(vg.ok_for_lvm_vg)

    def test_lv_ok_for_xxx(self):
        model, lv = make_model_and_lv()
        self.assertFalse(lv.ok_for_raid)
        self.assertFalse(lv.ok_for_lvm_vg)

    def test_get_orig_model_no_probe_data(self):
        # When v2/get_orig_data gets called early, model._probe_data is still
        # None. Ensure get_orig_model() does not fail.
        model = make_model()

        model._probe_data = None
        orig_model = model.get_orig_model()
        self.assertIsNone(orig_model._probe_data)

    @parameterized.expand(
        (
            (None, False, False),
            (None, True, True),
            (True, True, True),
            (True, False, True),
            (False, True, False),
            (False, False, False),
        )
    )
    def test_supports_nvme_tcp_booting(
        self, opt: bool | None, detected: bool, expected: bool
    ):
        model = make_model()
        model.opt_supports_nvme_tcp_booting = opt
        model.detected_supports_nvme_tcp_booting = detected
        self.assertEqual(expected, model.supports_nvme_tcp_booting)

    @parameterized.expand(
        (
            (True, True, True, True),
            (True, True, False, True),
            (True, False, False, True),
            (False, True, True, False),
            (False, True, False, True),
            (False, False, False, False),
        )
    )
    def test__can_install_remote(
        self,
        supports_nvmet_boot: bool,
        boot_mounted: bool,
        bootfs_remote: bool,
        expected: bool,
    ):
        model = make_model()
        p_supports_nvmet_boot = mock.patch(
            "subiquity.models.filesystem.FilesystemModel.supports_nvme_tcp_booting",
            new_callable=mock.PropertyMock,
            return_value=supports_nvmet_boot,
        )
        p_boot_mounted = mock.patch.object(
            model, "is_boot_mounted", return_value=boot_mounted
        )
        p_bootfs_remote = mock.patch.object(
            model, "is_bootfs_on_remote_storage", return_value=bootfs_remote
        )

        with (
            p_supports_nvmet_boot as m_supports_nvmet_boot,
            p_boot_mounted as m_boot_mounted,
            p_bootfs_remote as m_bootfs_remote,
        ):
            self.assertEqual(expected, model._can_install_remote())

        m_supports_nvmet_boot.assert_called_once()

        if supports_nvmet_boot:
            m_boot_mounted.assert_not_called()
            m_bootfs_remote.assert_not_called()
        else:
            m_boot_mounted.assert_called_once()
            if boot_mounted:
                m_bootfs_remote.assert_called_once()
            else:
                m_bootfs_remote.assert_not_called()

    @parameterized.expand(
        (
            (False, False, False, False, False),
            (True, False, False, False, True),
            (True, True, False, False, False),
            (True, True, True, False, True),
            (True, False, False, True, False),
        )
    )
    def test_can_install(
        self,
        root_mounted: bool,
        rootfs_remote: bool,
        can_install_remote: bool,
        needs_bootloader: bool,
        expected: bool,
    ):
        model = make_model()
        p_root_mounted = mock.patch.object(
            model, "is_root_mounted", return_value=root_mounted
        )
        p_rootfs_remote = mock.patch.object(
            model, "is_rootfs_on_remote_storage", return_value=rootfs_remote
        )
        p_can_install_remote = mock.patch.object(
            model, "_can_install_remote", return_value=can_install_remote
        )
        p_needs_bootloader = mock.patch.object(
            model, "needs_bootloader_partition", return_value=needs_bootloader
        )

        with (
            p_root_mounted as m_root_mounted,
            p_rootfs_remote as m_rootfs_remote,
            p_can_install_remote as m_can_install_remote,
            p_needs_bootloader as m_needs_bootloader,
        ):
            self.assertEqual(expected, model.can_install())

        m_root_mounted.assert_called_once()

        if root_mounted:
            m_rootfs_remote.assert_called_once()
        else:
            m_rootfs_remote.assert_not_called()

        if root_mounted and rootfs_remote:
            m_can_install_remote.assert_called_once()
        else:
            m_can_install_remote.assert_not_called()

        if root_mounted and (not rootfs_remote or can_install_remote):
            m_needs_bootloader.assert_called_once()
        else:
            m_needs_bootloader.assert_not_called()


def fake_up_blockdata_disk(disk, **kw):
    model = disk._m
    if model._probe_data is None:
        model._probe_data = {}
    blockdev = model._probe_data.setdefault("blockdev", {})
    d = blockdev[disk.path] = {
        "DEVTYPE": "disk",
        "ID_SERIAL": disk.serial,
        "ID_MODEL": disk.model,
        "attrs": {
            "size": disk.size,
        },
    }
    d.update(kw)


def fake_up_blockdata(model):
    for disk in model.all_disks():
        fake_up_blockdata_disk(disk)


class TestAutoInstallConfig(unittest.TestCase):
    def test_basic(self):
        model, disk = make_model_and_disk()
        fake_up_blockdata(model)
        model.apply_autoinstall_config([{"type": "disk", "id": "disk0"}])
        [new_disk] = model.all_disks()
        self.assertIsNot(new_disk, disk)
        self.assertEqual(new_disk.serial, disk.serial)

    def test_largest(self):
        model = make_model()
        make_disk(model, serial="smaller", size=10 * (2**30))
        make_disk(model, serial="larger", size=11 * (2**30))
        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "match": {
                        "size": "largest",
                    },
                },
            ]
        )
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, "larger")

    def test_smallest(self):
        model = make_model()
        make_disk(model, serial="smaller", size=10 * (2**30))
        make_disk(model, serial="larger", size=11 * (2**30))
        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "match": {
                        "size": "smallest",
                    },
                },
            ]
        )
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, "smaller")

    def test_smallest_skips_zero_size(self):
        model = make_model()
        make_disk(model, serial="smallest", size=0)
        make_disk(model, serial="smaller", size=10 * (2**30))
        make_disk(model, serial="larger", size=11 * (2**30))
        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "match": {
                        "size": "smallest",
                    },
                },
            ]
        )
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, "smaller")

    def test_serial_exact(self):
        model = make_model()
        make_disk(model, serial="aaaa", path="/dev/aaa")
        make_disk(model, serial="bbbb", path="/dev/bbb")
        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "serial": "aaaa",
                },
            ]
        )
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.path, "/dev/aaa")

    def test_serial_glob(self):
        model = make_model()
        make_disk(model, serial="aaaa", path="/dev/aaa")
        make_disk(model, serial="bbbb", path="/dev/bbb")
        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "match": {
                        "serial": "a*",
                    },
                },
            ]
        )
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.path, "/dev/aaa")

    def test_path_exact(self):
        model = make_model()
        make_disk(model, serial="aaaa", path="/dev/aaa")
        make_disk(model, serial="bbbb", path="/dev/bbb")
        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "path": "/dev/aaa",
                },
            ]
        )
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, "aaaa")

    def test_path_glob(self):
        model = make_model()
        d1 = make_disk(model, serial="aaaa", path="/dev/aaa")
        d2 = make_disk(model, serial="bbbb", path="/dev/bbb")
        fake_up_blockdata_disk(d1)
        fake_up_blockdata_disk(d2)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "match": {
                        "path": "/dev/a*",
                    },
                },
            ]
        )
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, d1.serial)

    def test_model_glob(self):
        model = make_model()
        d1 = make_disk(model, serial="aaaa")
        d2 = make_disk(model, serial="bbbb")
        fake_up_blockdata_disk(d1, ID_MODEL="aaa")
        fake_up_blockdata_disk(d2, ID_MODEL="bbb")
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "match": {
                        "model": "a*",
                    },
                },
            ]
        )
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, d1.serial)

    def test_vendor_glob(self):
        model = make_model()
        d1 = make_disk(model, serial="aaaa")
        d2 = make_disk(model, serial="bbbb")
        fake_up_blockdata_disk(d1, ID_VENDOR="aaa")
        fake_up_blockdata_disk(d2, ID_VENDOR="bbb")
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "match": {
                        "vendor": "a*",
                    },
                },
            ]
        )
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, d1.serial)

    def test_id_path_glob(self):
        model = make_model()
        d1 = make_disk(model, serial="aaaa")
        d2 = make_disk(model, serial="bbbb")
        fake_up_blockdata_disk(d1, ID_PATH="pci-0000:00:00.0-nvme-aaa")
        fake_up_blockdata_disk(d2, ID_PATH="pci-0000:00:00.0-nvme-bbb")
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "match": {
                        "id_path": "*aaa",
                    },
                },
            ]
        )
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, d1.serial)

    def test_devpath_glob(self):
        model = make_model()
        d1 = make_disk(model, serial="aaaa")
        d2 = make_disk(model, serial="bbbb")
        fake_up_blockdata_disk(d1, DEVPATH="/devices/pci0000:00/aaa")
        fake_up_blockdata_disk(d2, DEVPATH="/devices/pci0000:00/bbb")
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "match": {
                        "devpath": "*aaa",
                    },
                },
            ]
        )
        new_disk = model._one(type="disk", id="disk0")
        self.assertEqual(new_disk.serial, d1.serial)

    def test_no_matching_disk(self):
        model = make_model()
        make_disk(model, serial="bbbb")
        fake_up_blockdata(model)
        with self.assertRaises(Exception) as cm:
            model.apply_autoinstall_config(
                [
                    {
                        "type": "disk",
                        "id": "disk0",
                        "serial": "aaaa",
                    }
                ]
            )
        self.assertIn("matched no disk", str(cm.exception))

    def test_reuse_disk(self):
        model = make_model()
        make_disk(model, serial="aaaa")
        fake_up_blockdata(model)
        with self.assertRaises(Exception) as cm:
            model.apply_autoinstall_config(
                [
                    {
                        "type": "disk",
                        "id": "disk0",
                        "serial": "aaaa",
                    },
                    {
                        "type": "disk",
                        "id": "disk0",
                        "serial": "aaaa",
                    },
                ]
            )
        self.assertIn("was already used", str(cm.exception))

    def test_partition_percent(self):
        model = make_model()
        make_disk(model, serial="aaaa", size=dehumanize_size("100M"))
        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                },
                {
                    "type": "partition",
                    "id": "part0",
                    "device": "disk0",
                    "size": "50%",
                },
            ]
        )
        disk = model._one(type="disk")
        part = model._one(type="partition")
        self.assertEqual(part.size, disk.available_for_partitions // 2)

    def test_partition_remaining(self):
        model = make_model()
        make_disk(model, serial="aaaa", size=dehumanize_size("100M"))
        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                },
                {
                    "type": "partition",
                    "id": "part0",
                    "device": "disk0",
                    "size": dehumanize_size("50M"),
                },
                {
                    "type": "partition",
                    "id": "part1",
                    "device": "disk0",
                    "size": -1,
                },
            ]
        )
        disk = model._one(type="disk")
        part1 = model._one(type="partition", id="part1")
        self.assertEqual(
            part1.size, disk.available_for_partitions - dehumanize_size("50M")
        )

    def test_partition_not_final_remaining_size(self):
        model = make_model()
        make_disk(model, serial="aaaa", size=dehumanize_size("100M"))
        fake_up_blockdata(model)
        with self.assertRaises(NotFinalPartitionError):
            model.apply_autoinstall_config(
                [
                    {
                        "type": "disk",
                        "id": "disk0",
                    },
                    {
                        "type": "partition",
                        "id": "part0",
                        "device": "disk0",
                        "size": dehumanize_size("50M"),
                    },
                    {
                        "type": "partition",
                        "id": "part1",
                        "device": "disk0",
                        "size": -1,
                    },
                    {
                        "type": "partition",
                        "id": "part2",
                        "device": "disk0",
                        "size": dehumanize_size("10M"),
                    },
                ]
            )

    def test_extended_partition_remaining_size(self):
        model = make_model(bootloader=Bootloader.BIOS, storage_version=2)
        make_disk(model, serial="aaaa", size=dehumanize_size("100M"))

        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "ptable": "msdos",
                },
                {
                    "type": "partition",
                    "id": "part0",
                    "device": "disk0",
                    "size": dehumanize_size("40M"),
                },
                {
                    "type": "partition",
                    "id": "part1",
                    "device": "disk0",
                    "size": -1,
                    "flag": "extended",
                },
                {
                    "type": "partition",
                    "number": 5,
                    "id": "part5",
                    "device": "disk0",
                    "size": dehumanize_size("10M"),
                    "flag": "logical",
                },
            ]
        )
        extended = model._one(type="partition", id="part1")
        # Disk test.img: 100 MiB, 104857600 bytes, 204800 sectors
        # Units: sectors of 1 * 512 = 512 bytes
        # Sector size (logical/physical): 512 bytes / 512 bytes
        # I/O size (minimum/optimal): 512 bytes / 512 bytes
        # Disklabel type: dos
        # Disk identifier: 0x2cbec179
        #
        # Device     Boot Start    End Sectors Size Id Type
        # test.img1        2048  83967   81920  40M 83 Linux
        # test.img2       83968 204799  120832  59M  5 Extended
        # test.img5       86016 106495   20480  10M 83 Linux
        self.assertEqual(extended.size, 120832 * 512)

    def test_logical_partition_remaining_size(self):
        model = make_model(bootloader=Bootloader.BIOS, storage_version=2)
        make_disk(model, serial="aaaa", size=dehumanize_size("100M"))

        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "ptable": "msdos",
                },
                {
                    "type": "partition",
                    "id": "part0",
                    "device": "disk0",
                    "size": dehumanize_size("40M"),
                    "flag": "extended",
                },
                {
                    "type": "partition",
                    "number": 5,
                    "id": "part5",
                    "device": "disk0",
                    "size": -1,
                    "flag": "logical",
                },
            ]
        )
        disk = model._one(type="disk")
        extended = model._one(type="partition", id="part0")
        logical = model._one(type="partition", id="part5")

        ebr_space = disk.alignment_data().ebr_space
        # Disk test.img: 100 MiB, 104857600 bytes, 204800 sectors
        # Units: sectors of 1 * 512 = 512 bytes
        # Sector size (logical/physical): 512 bytes / 512 bytes
        # I/O size (minimum/optimal): 512 bytes / 512 bytes
        # Disklabel type: dos
        # Disk identifier: 0x16011ba9
        #
        # Device     Boot Start   End Sectors Size Id Type
        # test.img1        2048 83967   81920  40M  5 Extended
        # test.img5        4096 83967   79872  39M 83 Linux

        # At this point, there should be one large gap outside the extended
        # partition and a smaller one inside the extended partition.
        # Make sure our logical partition picks up the smaller one.

        self.assertEqual(extended.offset, 2048 * 512)
        self.assertEqual(logical.offset, 4096 * 512)
        self.assertEqual(logical.size, extended.size - ebr_space)

    def test_partition_remaining_size_in_extended_and_logical(self):
        model = make_model(bootloader=Bootloader.BIOS, storage_version=2)
        make_disk(model, serial="aaaa", size=dehumanize_size("100M"))
        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "ptable": "msdos",
                },
                {
                    "type": "partition",
                    "id": "part0",
                    "device": "disk0",
                    "size": dehumanize_size("40M"),
                },
                {
                    "type": "partition",
                    "id": "part1",
                    "device": "disk0",
                    "size": -1,
                    "flag": "extended",
                },
                {
                    "type": "partition",
                    "number": 5,
                    "id": "part5",
                    "device": "disk0",
                    "size": dehumanize_size("10M"),
                    "flag": "logical",
                },
                {
                    "type": "partition",
                    "number": 6,
                    "id": "part6",
                    "device": "disk0",
                    "size": -1,
                    "flag": "logical",
                },
            ]
        )
        extended = model._one(type="partition", id="part1")
        p5 = model._one(type="partition", id="part5")
        p6 = model._one(type="partition", id="part6")
        # Disk test.img: 100 MiB, 104857600 bytes, 204800 sectors
        # Units: sectors of 1 * 512 = 512 bytes
        # Sector size (logical/physical): 512 bytes / 512 bytes
        # I/O size (minimum/optimal): 512 bytes / 512 bytes
        # Disklabel type: dos
        # Disk identifier: 0x0b01e1ca
        #
        # Device     Boot  Start    End Sectors Size Id Type
        # test.img1         2048  83967   81920  40M 83 Linux
        # test.img2        83968 204799  120832  59M  5 Extended
        # test.img5        86016 106495   20480  10M 83 Linux
        # test.img6       108544 204799   96256  47M 83 Linux

        self.assertEqual(extended.offset, 83968 * 512)
        self.assertEqual(extended.size, 120832 * 512)
        self.assertEqual(p5.offset, 86016 * 512)
        self.assertEqual(p6.offset, 108544 * 512)
        self.assertEqual(p6.size, 96256 * 512)

    def test_partition_remaining_size_in_extended_and_logical_multiple(self):
        model = make_model(bootloader=Bootloader.BIOS, storage_version=2)
        make_disk(model, serial="aaaa", size=dehumanize_size("20G"))
        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                    "ptable": "msdos",
                },
                {
                    "type": "partition",
                    "flag": "boot",
                    "device": "disk0",
                    "size": dehumanize_size("1G"),
                    "id": "partition-boot",
                },
                {
                    "type": "partition",
                    "device": "disk0",
                    "size": dehumanize_size("6G"),
                    "id": "partition-root",
                },
                {
                    "type": "partition",
                    "device": "disk0",
                    "size": dehumanize_size("100M"),
                    "id": "partition-swap",
                },
                {
                    "type": "partition",
                    "device": "disk0",
                    "size": -1,
                    "flag": "extended",
                    "id": "partition-extended",
                },
                {
                    "type": "partition",
                    "device": "disk0",
                    "size": dehumanize_size("1G"),
                    "flag": "logical",
                    "id": "partition-tmp",
                },
                {
                    "type": "partition",
                    "device": "disk0",
                    "size": dehumanize_size("2G"),
                    "flag": "logical",
                    "id": "partition-var",
                },
                {
                    "type": "partition",
                    "device": "disk0",
                    "size": -1,
                    "flag": "logical",
                    "id": "partition-home",
                },
            ]
        )
        p_boot = model._one(type="partition", id="partition-boot")
        p_root = model._one(type="partition", id="partition-root")
        p_swap = model._one(type="partition", id="partition-swap")
        p_extended = model._one(type="partition", id="partition-extended")
        p_tmp = model._one(type="partition", id="partition-tmp")
        p_var = model._one(type="partition", id="partition-var")
        p_home = model._one(type="partition", id="partition-home")

        # Disk test.img: 20 GiB, 21474836480 bytes, 41943040 sectors
        # Units: sectors of 1 * 512 = 512 bytes
        # Sector size (logical/physical): 512 bytes / 512 bytes
        # I/O size (minimum/optimal): 512 bytes / 512 bytes
        # Disklabel type: dos
        # Disk identifier: 0xfbc457e5
        #
        # Device     Boot    Start      End  Sectors  Size Id Type
        # test.img1           2048  2099199  2097152    1G 83 Linux
        # test.img2        2099200 14682111 12582912    6G 83 Linux
        # test.img3       14682112 14886911   204800  100M 82 Linux swap ...
        # test.img4       14886912 41943039 27056128 12,9G  5 Extended
        # test.img5       14888960 16986111  2097152    1G 83 Linux
        # test.img6       16988160 21182463  4194304    2G 83 Linux
        # test.img7       21184512 41943039 20758528  9,9G 83 Linux
        self.assertEqual(p_boot.offset, 2048 * 512)
        self.assertEqual(p_boot.size, 2097152 * 512)
        self.assertEqual(p_root.offset, 2099200 * 512)
        self.assertEqual(p_root.size, 12582912 * 512)
        self.assertEqual(p_swap.offset, 14682112 * 512)
        self.assertEqual(p_swap.size, 204800 * 512)
        self.assertEqual(p_extended.offset, 14886912 * 512)
        self.assertEqual(p_extended.size, 27056128 * 512)
        self.assertEqual(p_tmp.offset, 14888960 * 512)
        self.assertEqual(p_tmp.size, 2097152 * 512)
        self.assertEqual(p_var.offset, 16988160 * 512)
        self.assertEqual(p_var.size, 4194304 * 512)
        self.assertEqual(p_home.offset, 21184512 * 512)
        self.assertEqual(p_home.size, 20758528 * 512)

    def test_lv_percent(self):
        model = make_model()
        make_disk(model, serial="aaaa", size=dehumanize_size("100M"))
        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                },
                {
                    "type": "lvm_volgroup",
                    "id": "vg0",
                    "name": "vg0",
                    "devices": ["disk0"],
                },
                {
                    "type": "lvm_partition",
                    "id": "lv1",
                    "name": "lv1",
                    "volgroup": "vg0",
                    "size": "50%",
                },
            ]
        )
        vg = model._one(type="lvm_volgroup")
        lv1 = model._one(type="lvm_partition")
        self.assertEqual(lv1.size, vg.available_for_partitions // 2)

    def test_lv_remaining(self):
        model = make_model()
        make_disk(model, serial="aaaa", size=dehumanize_size("100M"))
        fake_up_blockdata(model)
        model.apply_autoinstall_config(
            [
                {
                    "type": "disk",
                    "id": "disk0",
                },
                {
                    "type": "lvm_volgroup",
                    "id": "vg0",
                    "name": "vg0",
                    "devices": ["disk0"],
                },
                {
                    "type": "lvm_partition",
                    "id": "lv1",
                    "name": "lv1",
                    "volgroup": "vg0",
                    "size": dehumanize_size("50M"),
                },
                {
                    "type": "lvm_partition",
                    "id": "lv2",
                    "name": "lv2",
                    "volgroup": "vg0",
                    "size": -1,
                },
            ]
        )
        vg = model._one(type="lvm_volgroup")
        lv2 = model._one(type="lvm_partition", id="lv2")
        self.assertEqual(
            lv2.size,
            align_down(
                vg.available_for_partitions - dehumanize_size("50M"), LVM_CHUNK_SIZE
            ),
        )

    def test_render_does_not_include_unreferenced(self):
        model = make_model(Bootloader.NONE)
        disk1 = make_disk(model, preserve=True)
        disk2 = make_disk(model, preserve=True)
        disk1p1 = make_partition(model, disk1, preserve=True)
        disk2p1 = make_partition(model, disk2, preserve=True)
        fs = model.add_filesystem(disk1p1, "ext4")
        model.add_mount(fs, "/")
        rendered_ids = {action["id"] for action in model._render_actions()}
        self.assertTrue(disk1.id in rendered_ids)
        self.assertTrue(disk1p1.id in rendered_ids)
        self.assertTrue(disk2.id not in rendered_ids)
        self.assertTrue(disk2p1.id not in rendered_ids)

    def test_render_for_api_does_include_unreferenced(self):
        model = make_model(Bootloader.NONE)
        disk1 = make_disk(model, preserve=True)
        disk2 = make_disk(model, preserve=True)
        disk1p1 = make_partition(model, disk1, preserve=True)
        disk2p1 = make_partition(model, disk2, preserve=True)
        fs = model.add_filesystem(disk1p1, "ext4")
        model.add_mount(fs, "/")
        rendered_ids = {
            action["id"] for action in model._render_actions(ActionRenderMode.FOR_API)
        }
        self.assertTrue(disk1.id in rendered_ids)
        self.assertTrue(disk1p1.id in rendered_ids)
        self.assertTrue(disk2.id in rendered_ids)
        self.assertTrue(disk2p1.id in rendered_ids)

    def test_render_devices_skips_format_mount(self):
        model = make_model(Bootloader.NONE)
        disk1 = make_disk(model, preserve=True)
        disk1p1 = make_partition(model, disk1, preserve=True)
        fs = model.add_filesystem(disk1p1, "ext4")
        mnt = model.add_mount(fs, "/")
        rendered_ids = {
            action["id"] for action in model._render_actions(ActionRenderMode.DEVICES)
        }
        self.assertTrue(disk1.id in rendered_ids)
        self.assertTrue(disk1p1.id in rendered_ids)
        self.assertTrue(fs.id not in rendered_ids)
        self.assertTrue(mnt.id not in rendered_ids)

    def test_render_format_mount(self):
        model = make_model(Bootloader.NONE)
        disk1 = make_disk(model, preserve=True)
        disk1p1 = make_partition(model, disk1, preserve=True)
        disk1p1.path = "/dev/vda1"
        fs = model.add_filesystem(disk1p1, "ext4")
        mnt = model.add_mount(fs, "/")
        actions = model._render_actions(ActionRenderMode.FORMAT_MOUNT)
        rendered_by_id = {action["id"]: action for action in actions}
        self.assertTrue(disk1.id not in rendered_by_id)
        self.assertTrue(disk1p1.id not in rendered_by_id)
        self.assertTrue(fs.id in rendered_by_id)
        self.assertTrue(mnt.id in rendered_by_id)
        vol_id = rendered_by_id[fs.id]["volume"]
        self.assertEqual(rendered_by_id[vol_id]["type"], "device")
        self.assertEqual(rendered_by_id[vol_id]["path"], "/dev/vda1")

    def test_render_includes_all_partitions(self):
        model = make_model(Bootloader.NONE)
        disk1 = make_disk(model, preserve=True)
        disk1p1 = make_partition(
            model, disk1, preserve=True, offset=1 << 20, size=512 << 20
        )
        disk1p2 = make_partition(
            model, disk1, preserve=True, offset=513 << 20, size=8192 << 20
        )
        fs = model.add_filesystem(disk1p2, "ext4")
        model.add_mount(fs, "/")
        rendered_ids = {action["id"] for action in model._render_actions()}
        self.assertTrue(disk1.id in rendered_ids)
        self.assertTrue(disk1p1.id in rendered_ids)
        self.assertTrue(disk1p2.id in rendered_ids)

    def test_render_numbers_existing_partitions(self):
        model = make_model(Bootloader.NONE)
        disk1 = make_disk(model, preserve=True)
        disk1p1 = make_partition(model, disk1, preserve=True)
        fs = model.add_filesystem(disk1p1, "ext4")
        model.add_mount(fs, "/")
        actions = model._render_actions()
        for action in actions:
            if action["id"] != disk1p1.id:
                continue
            self.assertEqual(action["number"], 1)

    def test_render_includes_unmounted_new_partition(self):
        model = make_model(Bootloader.NONE)
        disk1 = make_disk(model, preserve=True)
        disk2 = make_disk(model)
        disk1p1 = make_partition(model, disk1, preserve=True)
        disk2p1 = make_partition(model, disk2)
        fs = model.add_filesystem(disk1p1, "ext4")
        model.add_mount(fs, "/")
        rendered_ids = {action["id"] for action in model._render_actions()}
        self.assertTrue(disk1.id in rendered_ids)
        self.assertTrue(disk1p1.id in rendered_ids)
        self.assertTrue(disk2.id in rendered_ids)
        self.assertTrue(disk2p1.id in rendered_ids)


class TestPartitionNumbering(unittest.TestCase):
    def setUp(self):
        self.cur_idx = 1

    def assert_next(self, part):
        self.assertEqual(self.cur_idx, part.number)
        self.cur_idx += 1

    def test_gpt(self):
        m, d1 = make_model_and_disk(ptable="gpt")
        for _ in range(8):
            self.assert_next(make_partition(m, d1))

    @parameterized.expand(
        [
            ["msdos", 4],
            ["vtoc", 3],
        ]
    )
    def test_all_primary(self, ptable, primaries):
        m = make_model(storage_version=2)
        d1 = make_disk(m, ptable=ptable)
        for _ in range(primaries):
            self.assert_next(make_partition(m, d1))

    @parameterized.expand(
        [
            ["msdos", 4],
            ["vtoc", 3],
        ]
    )
    def test_primary_and_extended(self, ptable, primaries):
        m = make_model(storage_version=2)
        d1 = make_disk(m, ptable=ptable)
        for _ in range(primaries - 1):
            self.assert_next(make_partition(m, d1))
        size = gaps.largest_gap_size(d1)
        self.assert_next(make_partition(m, d1, flag="extended", size=size))
        for _ in range(3):
            self.assert_next(make_partition(m, d1, flag="logical"))

    @parameterized.expand(
        [
            [pt, primaries, i]
            for pt, primaries in (("msdos", 4), ("vtoc", 3))
            for i in range(3)
        ]
    )
    def test_delete_logical(self, ptable, primaries, idx_to_remove):
        m = make_model(storage_version=2)
        d1 = make_disk(m, ptable=ptable)
        self.assert_next(make_partition(m, d1))
        size = gaps.largest_gap_size(d1)
        self.assert_next(make_partition(m, d1, flag="extended", size=size))
        self.cur_idx = primaries + 1
        parts = [make_partition(m, d1, flag="logical") for _ in range(3)]
        for p in parts:
            self.assert_next(p)
        to_remove = parts.pop(idx_to_remove)
        m.remove_partition(to_remove)
        self.cur_idx = primaries + 1
        for p in parts:
            self.assert_next(p)

    @parameterized.expand(
        [
            [pt, primaries, i]
            for pt, primaries in (("msdos", 4), ("vtoc", 3))
            for i in range(3)
        ]
    )
    def test_out_of_offset_order(self, ptable, primaries, idx_to_remove):
        m = make_model(storage_version=2)
        d1 = make_disk(m, ptable=ptable, size=100 << 20)
        self.assert_next(make_partition(m, d1, size=10 << 20))
        size = gaps.largest_gap_size(d1)
        self.assert_next(make_partition(m, d1, flag="extended", size=size))
        self.cur_idx = primaries + 1
        parts = []
        parts.append(
            make_partition(m, d1, flag="logical", size=9 << 20, offset=30 << 20)
        )
        parts.append(
            make_partition(m, d1, flag="logical", size=9 << 20, offset=20 << 20)
        )
        parts.append(
            make_partition(m, d1, flag="logical", size=9 << 20, offset=40 << 20)
        )
        for p in parts:
            self.assert_next(p)
        to_remove = parts.pop(idx_to_remove)
        m.remove_partition(to_remove)
        self.cur_idx = primaries + 1
        for p in parts:
            self.assert_next(p)

    @parameterized.expand(
        [
            [1, "msdos", 4],
            [1, "vtoc", 3],
            [2, "msdos", 4],
            [2, "vtoc", 3],
        ]
    )
    def test_no_extra_primary(self, sv, ptable, primaries):
        m = make_model(storage_version=sv)
        d1 = make_disk(m, ptable=ptable, size=100 << 30)
        for _ in range(primaries):
            self.assert_next(make_partition(m, d1, size=1 << 30))
        with self.assertRaises(Exception):
            make_partition(m, d1)

    @parameterized.expand([["gpt"], ["msdos"], ["vtoc"]])
    def test_p1_preserved(self, ptable):
        m = make_model(storage_version=2)
        d1 = make_disk(m, ptable=ptable)
        p1 = make_partition(m, d1, preserve=True, number=1)
        p2 = make_partition(m, d1)
        p3 = make_partition(m, d1)
        self.assertEqual(1, p1.number)
        self.assertEqual(True, p1.preserve)
        self.assertEqual(2, p2.number)
        self.assertEqual(False, p2.preserve)
        self.assertEqual(3, p3.number)
        self.assertEqual(False, p3.preserve)

    @parameterized.expand([["gpt"], ["msdos"], ["vtoc"]])
    def test_p2_preserved(self, ptable):
        m = make_model(storage_version=2)
        d1 = make_disk(m, ptable=ptable)
        p2 = make_partition(m, d1, preserve=True, number=2)
        p1 = make_partition(m, d1)
        p3 = make_partition(m, d1)
        self.assertEqual(1, p1.number)
        self.assertEqual(False, p1.preserve)
        self.assertEqual(2, p2.number)
        self.assertEqual(True, p2.preserve)
        self.assertEqual(3, p3.number)
        self.assertEqual(False, p3.preserve)


class TestAlignmentData(unittest.TestCase):
    @parameterized.expand([["gpt"], ["msdos"], ["vtoc"]])
    def test_alignment_gaps_coherence(self, ptable):
        d1 = make_disk(ptable=ptable)
        ad = d1.alignment_data()
        align_max = d1.size - ad.min_start_offset - ad.min_end_offset
        self.assertEqual(gaps.largest_gap_size(d1), align_max)


class TestSwap(unittest.TestCase):
    def test_basic(self):
        m = make_model()
        with mock.patch.object(m, "should_add_swapfile", return_value=False):
            cfg = m.render()
            self.assertEqual({"size": 0}, cfg["swap"])

    @parameterized.expand(
        [
            ["ext4"],
            ["btrfs"],
        ]
    )
    def test_should_add_swapfile_nomount(self, fs):
        m, d1 = make_model_and_disk(Bootloader.BIOS)
        d1p1 = make_partition(m, d1)
        m.add_filesystem(d1p1, fs)
        self.assertTrue(m.should_add_swapfile())

    @parameterized.expand(
        [
            ["ext4", None, True],
            ["btrfs", 5, True],
            ["btrfs", 4, False],
            ["zfs", None, False],
        ]
    )
    def test_should_add_swapfile(self, fs, kern_maj_ver, expected):
        m, d1 = make_model_and_disk(Bootloader.BIOS)
        d1p1 = make_partition(m, d1)
        m.add_mount(m.add_filesystem(d1p1, fs), "/")
        with mock.patch(
            "curtin.swap.get_target_kernel_version",
            return_value={"major": kern_maj_ver},
        ):
            self.assertEqual(expected, m.should_add_swapfile())

    def test_should_add_swapfile_has_swappart(self):
        m, d1 = make_model_and_disk(Bootloader.BIOS)
        d1p1 = make_partition(m, d1)
        d1p2 = make_partition(m, d1)
        m.add_mount(m.add_filesystem(d1p1, "ext4"), "/")
        m.add_mount(m.add_filesystem(d1p2, "swap"), "")
        self.assertFalse(m.should_add_swapfile())


class TestDisk(unittest.TestCase):
    def test_renumber_logical_partitions(self):
        m = make_model(storage_version=2)
        d = make_disk(m, ptable="msdos")

        pe = make_partition(m, d, flag="extended")
        pl1 = make_partition(m, d, flag="logical")
        pl2 = make_partition(m, d, flag="logical")
        pl3 = make_partition(m, d, flag="logical")
        pp = make_partition(m, d)

        self.assertEqual(1, pe.number)
        self.assertEqual(5, pl1.number)
        self.assertEqual(6, pl2.number)
        self.assertEqual(7, pl3.number)
        self.assertEqual(2, pp.number)

        d._partitions.remove(pl1)

        d.renumber_logical_partitions(removed_partition=pl1)

        self.assertEqual(1, pe.number)
        self.assertEqual(5, pl2.number)
        self.assertEqual(6, pl3.number)
        self.assertEqual(2, pp.number)

    def test_renumber_logical_partitions__after_removing_primary(self):
        m = make_model(storage_version=2)
        d = make_disk(m, ptable="msdos")

        make_partition(m, d, flag="extended")
        make_partition(m, d, flag="logical")
        pp = make_partition(m, d)

        d._partitions.remove(pp)

        with self.assertRaisesRegex(ValueError, r"^do not renumber"):
            d.renumber_logical_partitions(removed_partition=pp)

    def test__reformatted__empty_disk(self):
        m, d = make_model_and_disk()

        d2 = d._reformatted()
        self.assertIsNot(d, d2)
        self.assertIsNot(d._partitions, d2._partitions)

    def test__reformatted__with_partitions(self):
        m, d = make_model_and_disk()

        p1 = make_partition(m, d)
        p2 = make_partition(m, d)

        d2 = d._reformatted()

        self.assertIsNot(d, d2)
        self.assertEqual(d.partitions(), [p1, p2])
        self.assertEqual(d2.partitions(), [])

    def test__reformatted__with_in_use_parts(self):
        m, d = make_model_and_disk()

        p1 = make_partition(m, d, is_in_use=True)
        p2 = make_partition(m, d, is_in_use=True)
        p3 = make_partition(m, d)
        p4 = make_partition(m, d, is_in_use=True)
        p5 = make_partition(m, d)

        d2 = d._reformatted()

        self.assertIsNot(d, d2)
        self.assertEqual(d.partitions(), [p1, p2, p3, p4, p5])
        self.assertEqual(d2.partitions(), [p1, p2, p4])

    def test__excluding_partition(self):
        m, d = make_model_and_disk()

        p1 = make_partition(m, d)
        p2 = make_partition(m, d)

        d2 = d._excluding_partition(p1)

        self.assertIsNot(d, d2)
        self.assertEqual(d.partitions(), [p1, p2])
        self.assertEqual(d2.partitions(), [p2])


class TestPartition(unittest.TestCase):
    def test_is_logical(self):
        m = make_model(storage_version=2)
        d = make_disk(m, ptable="msdos")
        make_partition(m, d, flag="extended")
        p3 = make_partition(m, d, number=3, flag="swap")
        p4 = make_partition(m, d, number=4, flag="boot")

        p5 = make_partition(m, d, number=5, flag="logical")
        p6 = make_partition(m, d, number=6, flag="boot")
        p7 = make_partition(m, d, number=7, flag="swap")

        self.assertFalse(p3.is_logical)
        self.assertFalse(p4.is_logical)
        self.assertTrue(p5.is_logical)
        self.assertTrue(p6.is_logical)
        self.assertTrue(p7.is_logical)

    def test_os(self):
        m = make_model(storage_version=2)
        d = make_disk(m, ptable="gpt")

        p1 = make_partition(m, d, preserve=True)
        p2 = make_partition(m, d, preserve=True)

        os_info = {
            "label": "Ubuntu",
            "long": "Ubuntu 22.04.1 LTS",
            "type": "linux",
            "version": "22.04.1",
        }

        m._probe_data["os"] = {p1._path(): os_info}

        self.assertEqual("Ubuntu", p1.os.label)
        self.assertEqual("Ubuntu 22.04.1 LTS", p1.os.long)
        self.assertEqual("linux", p1.os.type)
        self.assertEqual("22.04.1", p1.os.version)
        self.assertIsNone(p1.os.subpath)
        self.assertIsNone(p2.os)

    def test_os__recreated_partition(self):
        m = make_model(storage_version=2)
        d = make_disk(m, ptable="gpt")

        # We do not mark the partition preserved, which means we either
        # formatted the disk or deleted / recreated the partition.
        p = make_partition(m, d)

        os_info = {
            "label": "Ubuntu",
            "long": "Ubuntu 22.04.1 LTS",
            "type": "linux",
            "version": "22.04.1",
        }

        m._probe_data["os"] = {p._path(): os_info}

        self.assertIsNone(p.os)


class TestCanmount(SubiTestCase):
    @parameterized.expand(
        (
            ("on", True),
            ('"on"', True),
            ("true", True),
            ("off", False),
            ('"off"', False),
            ("false", False),
            ("noauto", False),
            ('"noauto"', False),
        )
    )
    def test_present(self, value, expected):
        property_yaml = f"canmount: {value}"
        properties = yaml.safe_load(property_yaml)
        for default in (True, False):
            self.assertEqual(
                expected,
                get_canmount(properties, default),
                f"yaml {property_yaml} default {default}",
            )

    @parameterized.expand(
        (
            ["{}"],
            ["something-else: on"],
        )
    )
    def test_not_present(self, property_yaml):
        properties = yaml.safe_load(property_yaml)
        for default in (True, False):
            self.assertEqual(
                default,
                get_canmount(properties, default),
                f"yaml {property_yaml} default {default}",
            )

    @parameterized.expand(
        (
            ["asdf"],
            ['"true"'],
            ['"false"'],
        )
    )
    def test_invalid(self, value):
        with self.assertRaises(ValueError):
            properties = yaml.safe_load(f"canmount: {value}")
            get_canmount(properties, False)


class TestZPool(SubiTestCase):
    def test_zpool_to_action(self):
        m = make_model()
        d = make_disk(m)
        zp = make_zpool(model=m, device=d, mountpoint="/", pool="p1")
        zfs = make_zfs(model=m, pool=zp, volume="/ROOTFS")

        actions = m._render_actions()
        a_zp = dict(matching_dicts(actions, type="zpool")[0])
        a_zfs = dict(matching_dicts(actions, type="zfs")[0])
        e_zp = {
            "default_features": True,
            "vdevs": [d.id],
            "pool": "p1",
            "mountpoint": "/",
            "type": "zpool",
            "id": zp.id,
        }
        e_zfs = {"pool": zp.id, "volume": "/ROOTFS", "type": "zfs", "id": zfs.id}
        self.assertEqual(e_zp, a_zp)
        self.assertEqual(e_zfs, a_zfs)

    def test_zpool_from_action(self):
        m = make_model()
        d1 = make_disk(m)
        d2 = make_disk(m)
        fake_up_blockdata(m)
        blockdevs = m._probe_data["blockdev"]
        config = [
            dict(
                type="disk",
                id=d1.id,
                path=d1.path,
                ptable=d1.ptable,
                serial=d1.serial,
                info={d1.path: blockdevs[d1.path]},
            ),
            dict(
                type="disk",
                id=d2.id,
                path=d2.path,
                ptable=d2.ptable,
                serial=d2.serial,
                info={d2.path: blockdevs[d2.path]},
            ),
            dict(
                type="zpool",
                id="zpool-1",
                vdevs=[d1.id],
                pool="p1",
                mountpoint="/",
                fs_properties=dict(canmount="on"),
            ),
            dict(
                type="zpool",
                id="zpool-2",
                vdevs=[d2.id],
                pool="p2",
                mountpoint="/srv",
                fs_properties=dict(canmount="off"),
            ),
            dict(
                type="zfs",
                id="zfs-1",
                volume="/ROOT",
                pool="zpool-1",
                properties=dict(canmount="off"),
            ),
            dict(
                type="zfs",
                id="zfs-2",
                volume="/SRV/srv",
                pool="zpool-2",
                properties=dict(mountpoint="/srv", canmount="on"),
            ),
        ]
        objs = m._actions_from_config(config, blockdevs=None, is_probe_data=False)
        actual_d1, actual_d2, zp1, zp2, zfs_zp1, zfs_zp2 = objs
        self.assertTrue(isinstance(zp1, ZPool))
        self.assertEqual("zpool-1", zp1.id)
        self.assertEqual([actual_d1], zp1.vdevs)
        self.assertEqual("p1", zp1.pool)
        self.assertEqual("/", zp1.mountpoint)
        self.assertEqual("/", zp1.path)
        self.assertEqual([zfs_zp1], zp1._zfses)

        self.assertTrue(isinstance(zp2, ZPool))
        self.assertEqual("zpool-2", zp2.id)
        self.assertEqual([actual_d2], zp2.vdevs)
        self.assertEqual("p2", zp2.pool)
        self.assertEqual("/srv", zp2.mountpoint)
        self.assertEqual(None, zp2.path)
        self.assertEqual([zfs_zp2], zp2._zfses)

        self.assertTrue(isinstance(zfs_zp1, ZFS))
        self.assertEqual("zfs-1", zfs_zp1.id)
        self.assertEqual(zp1, zfs_zp1.pool)
        self.assertEqual("/ROOT", zfs_zp1.volume)
        self.assertEqual(None, zfs_zp1.path)

        self.assertTrue(isinstance(zfs_zp2, ZFS))
        self.assertEqual("zfs-2", zfs_zp2.id)
        self.assertEqual(zp2, zfs_zp2.pool)
        self.assertEqual("/SRV/srv", zfs_zp2.volume)
        self.assertEqual("/srv", zfs_zp2.path)


class TestRootfs(SubiTestCase):
    def test_mount_rootfs(self):
        m, p = make_model_and_partition()
        fs = make_filesystem(m, p)
        m.add_mount(fs, "/")
        self.assertTrue(m.is_root_mounted())

    def test_mount_srv(self):
        m, p = make_model_and_partition()
        fs = make_filesystem(m, p)
        m.add_mount(fs, "/srv")
        self.assertFalse(m.is_root_mounted())

    def test_zpool_not_rootfs_because_not_canmount(self):
        m = make_model()
        make_zpool(model=m, mountpoint="/", fs_properties=dict(canmount="off"))
        self.assertFalse(m.is_root_mounted())

    def test_zpool_rootfs_because_canmount(self):
        m = make_model()
        make_zpool(model=m, mountpoint="/", fs_properties=dict(canmount="on"))
        self.assertTrue(m.is_root_mounted())

    def test_zpool_nonrootfs_mountpoint(self):
        m = make_model()
        make_zpool(model=m, mountpoint="/srv")
        self.assertFalse(m.is_root_mounted())


class TestLivePackages(SubiTestCase):
    async def test_defaults(self):
        m = make_model()
        (before, during) = await m.live_packages()
        self.assertEqual(set(), before)
        self.assertEqual(set(), during)

    async def test_zfs(self):
        m = make_model()
        make_zpool(model=m, mountpoint="/")
        (before, during) = await m.live_packages()
        self.assertEqual(set(["zfsutils-linux"]), before)
        self.assertEqual(set(), during)

    async def test_efibootmgr(self):
        m = make_model()
        d = make_disk(m)
        m.reset_partition = make_partition(m, d)
        (before, during) = await m.live_packages()
        self.assertEqual(set(), before)
        self.assertEqual(set(["efibootmgr"]), during)

    async def test_both(self):
        m = make_model()
        d = make_disk(m)
        make_zpool(model=m, mountpoint="/")
        m.reset_partition = make_partition(m, d)
        (before, during) = await m.live_packages()
        self.assertEqual(set(["zfsutils-linux"]), before)
        self.assertEqual(set(["efibootmgr"]), during)


class TestRecoveryKeyHandler(SubiTestCase):
    def test_from_post_data_none(self):
        self.assertIsNone(RecoveryKeyHandler.from_post_data(None))

    def test_form_post_data_all_set(self):
        live_location = "/home/ubuntu/recovery-ubuntu-vg.txt"
        backup_location = "/var/log/installer/recovery-ubuntu-vg.txt"

        data = RecoveryKey(live_location=live_location, backup_location=backup_location)

        expected = RecoveryKeyHandler(
            live_location=pathlib.Path(live_location),
            backup_location=pathlib.Path(backup_location),
        )

        self.assertEqual(RecoveryKeyHandler.from_post_data(data), expected)

    def test_form_post_data_backup_use_default_suffix(self):
        live_location = "/home/ubuntu/recovery-ubuntu-vg.txt"

        data = RecoveryKey(live_location=live_location)

        expected = RecoveryKeyHandler(
            live_location=pathlib.Path(live_location),
            backup_location=pathlib.Path("/var/log/installer/recovery-key.txt"),
        )

        self.assertEqual(RecoveryKeyHandler.from_post_data(data), expected)

    def test_form_post_data_backup_override_default_suffix(self):
        live_location = "/home/ubuntu/recovery-ubuntu-vg.txt"

        data = RecoveryKey(live_location=live_location)

        expected = RecoveryKeyHandler(
            live_location=pathlib.Path(live_location),
            backup_location=pathlib.Path("/var/log/installer/mykey-ubuntu-vg.txt"),
        )

        self.assertEqual(
            RecoveryKeyHandler.from_post_data(
                data, default_suffix="mykey-ubuntu-vg.txt"
            ),
            expected,
        )


class TestOnRemoteStorage(SubiTestCase):
    def test_disk__on_local_storage(self):
        m, d = make_model_and_disk(name="sda", serial="sata0")
        self.assertFalse(d.on_remote_storage())

        d = make_disk(name="nvme0n1", serial="pcie0")
        self.assertFalse(d.on_remote_storage())

        ctrler = make_nvme_controller(model=m, transport="pcie")

        d = make_disk(
            fs_model=m, name="nvme1n1", nvme_controller=ctrler, serial="pcie1"
        )
        self.assertFalse(d.on_remote_storage())

    def test_disk__on_remote_storage(self):
        m = make_model()

        ctrler = make_nvme_controller(
            model=m, transport="tcp", tcp_addr="172.16.82.78", tcp_port=4420
        )

        d = make_disk(fs_model=m, name="nvme0n1", nvme_controller=ctrler, serial="tcp0")
        self.assertTrue(d.on_remote_storage())

    def test_partition(self):
        m, d = make_model_and_disk(name="sda", serial="sata0")
        p = make_partition(model=m, device=d)

        # For partitions, this is directly dependent on the underlying device.
        with mock.patch.object(d, "on_remote_storage", return_value=False):
            self.assertFalse(p.on_remote_storage())
        with mock.patch.object(d, "on_remote_storage", return_value=True):
            self.assertTrue(p.on_remote_storage())

    def test_raid(self):
        m, raid = make_model_and_raid()

        d0, d1 = list(raid.devices)

        d0_local = mock.patch.object(d0, "on_remote_storage", return_value=False)
        d1_local = mock.patch.object(d1, "on_remote_storage", return_value=False)
        d0_remote = mock.patch.object(d0, "on_remote_storage", return_value=True)
        d1_remote = mock.patch.object(d1, "on_remote_storage", return_value=True)

        # If at least one of the underlying disk is on remote storage, the raid
        # should be considered on remote storage too.
        with d0_local, d1_local:
            self.assertFalse(raid.on_remote_storage())
        with d0_local, d1_remote:
            self.assertTrue(raid.on_remote_storage())
        with d0_remote, d1_local:
            self.assertTrue(raid.on_remote_storage())
        with d0_remote, d1_remote:
            self.assertTrue(raid.on_remote_storage())

    def test_lvm_volgroup(self):
        m, vg = make_model_and_vg()

        # make_vg creates a VG with a single PV (i.e., a disk).
        d0 = vg.devices[0]

        with mock.patch.object(d0, "on_remote_storage", return_value=False):
            self.assertFalse(vg.on_remote_storage())
        with mock.patch.object(d0, "on_remote_storage", return_value=True):
            self.assertTrue(vg.on_remote_storage())

        d1 = make_disk(fs_model=m)

        vg.devices.append(d1)

        d0_local = mock.patch.object(d0, "on_remote_storage", return_value=False)
        d1_local = mock.patch.object(d1, "on_remote_storage", return_value=False)
        d0_remote = mock.patch.object(d0, "on_remote_storage", return_value=True)
        d1_remote = mock.patch.object(d1, "on_remote_storage", return_value=True)

        # Just like RAIDs, if at least one of the underlying PV is on remote
        # storage, the VG should be considered on remote storage too.
        with d0_local, d1_local:
            self.assertFalse(vg.on_remote_storage())
        with d0_local, d1_remote:
            self.assertTrue(vg.on_remote_storage())
        with d0_remote, d1_local:
            self.assertTrue(vg.on_remote_storage())
        with d0_remote, d1_remote:
            self.assertTrue(vg.on_remote_storage())

    def test_lvm_logical_volume(self):
        m, lv = make_model_and_lv()

        vg = lv.volgroup
        # For LVs, this is directly dependent on the underlying VG.
        with mock.patch.object(vg, "on_remote_storage", return_value=False):
            self.assertFalse(lv.on_remote_storage())
        with mock.patch.object(vg, "on_remote_storage", return_value=True):
            self.assertTrue(lv.on_remote_storage())


class TestDiskForMatch(SubiTestCase):
    match_sort_criteria = (["smallest"], ["largest"])

    def test_empty_match_directive(self):
        m = make_model()
        d1 = make_disk(m)
        d2 = make_disk(m)

        # this test relies heavily on the assumptions in make_disk
        self.assertEqual(d1, m.disk_for_match([d1, d2], {}))
        self.assertEqual([d1, d2], m.disks_for_match([d1, d2], {}))
        self.assertEqual(d1, m.disk_for_match([d2, d1], {}))
        self.assertEqual([d1, d2], m.disks_for_match([d2, d1], {}))

    def test_sort_largest(self):
        m = make_model()
        d100 = make_disk(m, size=100 << 30, serial="s1", path="/dev/d1")
        d200 = make_disk(m, size=200 << 30, serial="s2", path="/dev/d2")
        self.assertEqual(d200, m.disk_for_match([d100, d200], {"size": "largest"}))
        self.assertEqual(
            [d200, d100], m.disks_for_match([d100, d200], {"size": "largest"})
        )

    def test_sort_smallest(self):
        m = make_model()
        d200 = make_disk(m, size=200 << 30)
        d100 = make_disk(m, size=100 << 30)
        self.assertEqual(d100, m.disk_for_match([d200, d100], {"size": "smallest"}))
        self.assertEqual(
            [d100, d200], m.disks_for_match([d200, d100], {"size": "smallest"})
        )

    @parameterized.expand(match_sort_criteria)
    def test_sort_serial(self, sort_criteria: str):
        m = make_model()
        d1 = make_disk(m, serial="s1", path=None, wwn=None)
        d2 = make_disk(m, serial="s2", path=None, wwn=None)
        # while the size sort is reversed when doing largest,
        # we pre-sort on the other criteria, and stable sort helps out
        self.assertEqual(d1, m.disk_for_match([d2, d1], {"size": sort_criteria}))
        self.assertEqual([d1, d2], m.disks_for_match([d2, d1], {"size": sort_criteria}))

    @parameterized.expand(match_sort_criteria)
    def test_sort_path(self, sort_criteria: str):
        m = make_model()
        d1 = make_disk(m, serial=None, path="/dev/d1", wwn=None)
        d2 = make_disk(m, serial=None, path="/dev/d2", wwn=None)
        self.assertEqual(d1, m.disk_for_match([d2, d1], {"size": sort_criteria}))
        self.assertEqual([d1, d2], m.disks_for_match([d2, d1], {"size": sort_criteria}))

    @parameterized.expand(match_sort_criteria)
    def test_sort_wwn(self, sort_criteria: str):
        m = make_model()
        d1 = make_disk(m, serial=None, path=None, wwn="w1")
        d2 = make_disk(m, serial=None, path=None, wwn="w2")
        self.assertEqual(d1, m.disk_for_match([d2, d1], {"size": sort_criteria}))
        self.assertEqual([d1, d2], m.disks_for_match([d2, d1], {"size": sort_criteria}))

    @parameterized.expand(match_sort_criteria)
    def test_sort_wwn_wins(self, sort_criteria: str):
        m = make_model()
        d1 = make_disk(m, serial="s2", path="/dev/d2", wwn="w1")
        d2 = make_disk(m, serial="s1", path="/dev/d1", wwn="w2")
        self.assertEqual(d1, m.disk_for_match([d2, d1], {"size": sort_criteria}))
        self.assertEqual([d1, d2], m.disks_for_match([d2, d1], {"size": sort_criteria}))

    @parameterized.expand(match_sort_criteria)
    def test_sort_serial_wins(self, sort_criteria: str):
        m = make_model()
        d1 = make_disk(m, serial="s1", path="/dev/d2", wwn="w")
        d2 = make_disk(m, serial="s2", path="/dev/d1", wwn="w")
        self.assertEqual(d1, m.disk_for_match([d2, d1], {"size": sort_criteria}))
        self.assertEqual([d1, d2], m.disks_for_match([d2, d1], {"size": sort_criteria}))

    @parameterized.expand(match_sort_criteria)
    def test_sort_path_wins(self, sort_criteria: str):
        m = make_model()
        d1 = make_disk(m, serial="s", path="/dev/d1", wwn="w")
        d2 = make_disk(m, serial="s", path="/dev/d2", wwn="w")
        self.assertEqual(d1, m.disk_for_match([d2, d1], {"size": sort_criteria}))
        self.assertEqual([d1, d2], m.disks_for_match([d2, d1], {"size": sort_criteria}))

    def test_sort_raid(self):
        m = make_model()
        d1_1 = make_disk(m, size=100 << 30)
        d1_2 = make_disk(m, size=100 << 30)
        d2_1 = make_disk(m, size=200 << 30)
        d2_2 = make_disk(m, size=200 << 30)
        r1 = make_raid(m, disks={d1_1, d1_2})
        r2 = make_raid(m, disks={d2_1, d2_2})
        self.assertEqual(r2, m.disk_for_match([r1, r2], {"size": "largest"}))
        self.assertEqual([r2, r1], m.disks_for_match([r1, r2], {"size": "largest"}))

    @parameterized.expand(match_sort_criteria)
    def test_sort_raid_on_disks(self, sort_criteria: str):
        m = make_model()
        d1_1 = make_disk(m, serial=None, path=None, wwn="w1_1")
        d1_2 = make_disk(m, serial=None, path=None, wwn="w1_2")
        d2_1 = make_disk(m, serial=None, path=None, wwn="w2_1")
        d2_2 = make_disk(m, serial=None, path=None, wwn="w2_2")
        r1 = make_raid(m, disks={d1_1, d1_2})
        r2 = make_raid(m, disks={d2_1, d2_2})
        self.assertEqual(r1, m.disk_for_match([r1, r2], {"size": sort_criteria}))
        self.assertEqual([r1, r2], m.disks_for_match([r1, r2], {"size": sort_criteria}))

    def test_skip_empty(self):
        m = make_model()
        d0 = make_disk(m, size=0)
        d100 = make_disk(m, size=100 << 30)
        self.assertEqual(d100, m.disk_for_match([d0, d100], {"size": "smallest"}))
        self.assertEqual([d100], m.disks_for_match([d0, d100], {"size": "smallest"}))

    def test_skip_in_use_size(self):
        m = make_model()
        d100 = make_disk(m, size=100 << 30)
        d200 = make_disk(m, size=200 << 30)
        d100._has_in_use_partition = True
        self.assertEqual(d200, m.disk_for_match([d100, d200], {"size": "smallest"}))
        self.assertEqual([d200], m.disks_for_match([d100, d200], {"size": "smallest"}))

    def test_skip_in_use_ssd(self):
        m = make_model()
        d_in_use = make_disk(m)
        d_not_used = make_disk(m)
        d_in_use._has_in_use_partition = True
        d_in_use.info_for_display = Mock(return_value={"rotational": "false"})
        d_not_used.info_for_display = Mock(return_value={"rotational": "false"})
        self.assertEqual(
            d_not_used, m.disk_for_match([d_in_use, d_not_used], {"ssd": True})
        )
        self.assertEqual(
            [d_not_used], m.disks_for_match([d_in_use, d_not_used], {"ssd": True})
        )

    def test_matcher_serial(self):
        m = make_model()
        d1 = make_disk(m, serial="1")
        d2 = make_disk(m, serial="2")
        fake_up_blockdata(m)
        self.assertEqual(d1, m.disk_for_match([d1, d2], {"serial": "1"}))
        self.assertEqual([d1], m.disks_for_match([d1, d2], {"serial": "1"}))
        self.assertEqual(d2, m.disk_for_match([d1, d2], {"serial": "2"}))
        self.assertEqual([d2], m.disks_for_match([d1, d2], {"serial": "2"}))

    def test_matcher_model(self):
        m = make_model()
        d1 = make_disk(m)
        fake_up_blockdata_disk(d1, ID_MODEL="m1")
        d2 = make_disk(m)
        fake_up_blockdata_disk(d2, ID_MODEL="m2")
        self.assertEqual(d1, m.disk_for_match([d1, d2], {"model": "m1"}))
        self.assertEqual([d1], m.disks_for_match([d1, d2], {"model": "m1"}))
        self.assertEqual(d2, m.disk_for_match([d1, d2], {"model": "m2"}))
        self.assertEqual([d2], m.disks_for_match([d1, d2], {"model": "m2"}))

    def test_matcher_vendor(self):
        m = make_model()
        d1 = make_disk(m)
        fake_up_blockdata_disk(d1, ID_VENDOR="v1")
        d2 = make_disk(m)
        fake_up_blockdata_disk(d2, ID_VENDOR="v2")
        self.assertEqual(d1, m.disk_for_match([d1, d2], {"vendor": "v1"}))
        self.assertEqual([d1], m.disks_for_match([d1, d2], {"vendor": "v1"}))
        self.assertEqual(d2, m.disk_for_match([d1, d2], {"vendor": "v2"}))
        self.assertEqual([d2], m.disks_for_match([d1, d2], {"vendor": "v2"}))

    def test_matcher_path(self):
        m = make_model()
        vda = make_disk(m, path="/dev/vda")
        vdb = make_disk(m, path="/dev/vdb")
        fake_up_blockdata(m)
        self.assertEqual(vda, m.disk_for_match([vda, vdb], {"path": "/dev/vda"}))
        self.assertEqual([vda], m.disks_for_match([vda, vdb], {"path": "/dev/vda"}))
        self.assertEqual(vdb, m.disk_for_match([vda, vdb], {"path": "/dev/vdb"}))
        self.assertEqual([vdb], m.disks_for_match([vda, vdb], {"path": "/dev/vdb"}))

    def test_matcher_id_path(self):
        m = make_model()
        vda = make_disk(m)
        fake_up_blockdata_disk(vda, ID_PATH="pci-0000:00:00.0-nvme-vda")
        vdb = make_disk(m)
        fake_up_blockdata_disk(vdb, ID_PATH="pci-0000:00:00.0-nvme-vdb")
        self.assertEqual(vda, m.disk_for_match([vda, vdb], {"id_path": "*vda"}))
        self.assertEqual([vda], m.disks_for_match([vda, vdb], {"id_path": "*vda"}))
        self.assertEqual(vdb, m.disk_for_match([vda, vdb], {"id_path": "*vdb"}))
        self.assertEqual([vdb], m.disks_for_match([vda, vdb], {"id_path": "*vdb"}))

    def test_matcher_install_media(self):
        m = make_model()
        iso = make_disk(m)
        iso._has_in_use_partition = True
        disk = make_disk(m)
        fake_up_blockdata(m)
        self.assertEqual(iso, m.disk_for_match([iso, disk], {"install-media": True}))
        self.assertEqual([iso], m.disks_for_match([iso, disk], {"install-media": True}))

    def test_match_from_list_first(self):
        m = make_model()
        vda = make_disk(m, path="/dev/vda", serial="s1")
        vdb = make_disk(m, path="/dev/vdb", serial="s2")
        fake_up_blockdata(m)
        match = [
            {"serial": "s1"},
            {"path": "/dev/vdb"},
        ]
        self.assertEqual(vda, m.disk_for_match([vda, vdb], match))
        self.assertEqual([vda], m.disks_for_match([vda, vdb], match))

    def test_match_from_list_second(self):
        m = make_model()
        vda = make_disk(m, path="/dev/vda", serial="s1")
        vdb = make_disk(m, path="/dev/vdb", serial="s2")
        fake_up_blockdata(m)
        match = [
            {"serial": "not-found"},
            {"path": "/dev/vdb"},
        ]
        self.assertEqual(vdb, m.disk_for_match([vda, vdb], match))
        self.assertEqual([vdb], m.disks_for_match([vda, vdb], match))
