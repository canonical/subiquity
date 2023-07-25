# Copyright 2022 Canonical, Ltd.
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

import copy
import uuid
from unittest import IsolatedAsyncioTestCase, mock

from curtin.commands.extract import TrivialSourceHandler

from subiquity.common.filesystem import gaps, labels
from subiquity.common.filesystem.actions import DeviceAction
from subiquity.common.types import (
    AddPartitionV2,
    Bootloader,
    Gap,
    GapUsable,
    GuidedCapability,
    GuidedChoiceV2,
    GuidedDisallowedCapability,
    GuidedDisallowedCapabilityReason,
    GuidedStorageTargetManual,
    GuidedStorageTargetReformat,
    GuidedStorageTargetResize,
    GuidedStorageTargetUseGap,
    ModifyPartitionV2,
    Partition,
    ProbeStatus,
    ReformatDisk,
    SizingPolicy,
)
from subiquity.models.filesystem import dehumanize_size
from subiquity.models.source import CatalogEntryVariation
from subiquity.models.tests.test_filesystem import (
    FakeStorageInfo,
    make_disk,
    make_model,
    make_partition,
)
from subiquity.server import snapdapi
from subiquity.server.controllers.filesystem import (
    DRY_RUN_RESET_SIZE,
    FilesystemController,
    VariationInfo,
)
from subiquity.server.dryrun import DRConfig
from subiquitycore.snapd import AsyncSnapd, get_fake_connection
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized
from subiquitycore.tests.util import random_string
from subiquitycore.utils import matching_dicts

bootloaders = [(bl,) for bl in list(Bootloader)]
bootloaders_and_ptables = [
    (bl, pt) for bl in list(Bootloader) for pt in ("gpt", "msdos", "vtoc")
]


default_capabilities = [
    GuidedCapability.DIRECT,
    GuidedCapability.LVM,
    GuidedCapability.LVM_LUKS,
    GuidedCapability.ZFS,
]


default_capabilities_disallowed_too_small = [
    GuidedDisallowedCapability(
        capability=cap, reason=GuidedDisallowedCapabilityReason.TOO_SMALL
    )
    for cap in default_capabilities
]


class TestSubiquityControllerFilesystem(IsolatedAsyncioTestCase):
    MOCK_PREFIX = "subiquity.server.controllers.filesystem."

    def setUp(self):
        self.app = make_app()
        self.app.opts.bootloader = "UEFI"
        self.app.report_start_event = mock.Mock()
        self.app.report_finish_event = mock.Mock()
        self.app.prober = mock.Mock()
        self.app.prober.get_storage = mock.AsyncMock()
        self.app.block_log_dir = "/inexistent"
        self.app.note_file_for_apport = mock.Mock()
        self.fsc = FilesystemController(app=self.app)
        self.fsc._configured = True

    async def test_probe_restricted(self):
        await self.fsc._probe_once(context=None, restricted=True)
        expected = {"blockdev", "filesystem"}
        self.app.prober.get_storage.assert_called_with(expected)

    async def test_probe_os_prober_false(self):
        self.app.opts.use_os_prober = False
        await self.fsc._probe_once(context=None, restricted=False)
        actual = self.app.prober.get_storage.call_args.args[0]
        self.assertTrue({"defaults"} <= actual)
        self.assertNotIn("os", actual)

    async def test_probe_os_prober_true(self):
        self.app.opts.use_os_prober = True
        await self.fsc._probe_once(context=None, restricted=False)
        actual = self.app.prober.get_storage.call_args.args[0]
        self.assertTrue({"defaults", "os"} <= actual)

    async def test_probe_once_fs_configured(self):
        self.fsc._configured = True
        self.fsc.queued_probe_data = None
        with mock.patch.object(self.fsc.model, "load_probe_data") as load:
            await self.fsc._probe_once(restricted=True)
        self.assertIsNone(self.fsc.queued_probe_data)
        load.assert_not_called()

    async def test_layout_no_grub_or_swap(self):
        self.fsc.model = model = make_model(Bootloader.UEFI)
        self.fsc.run_autoinstall_guided = mock.AsyncMock()

        self.fsc.ai_data = {
            "layout": {"name": "direct"},
        }

        await self.fsc.convert_autoinstall_config()
        curtin_cfg = model.render()
        self.assertNotIn("grub", curtin_cfg)
        self.assertNotIn("swap", curtin_cfg)

    @parameterized.expand(((True,), (False,)))
    async def test_layout_plus_grub(self, reorder_uefi):
        self.fsc.model = model = make_model(Bootloader.UEFI)
        self.fsc.run_autoinstall_guided = mock.AsyncMock()

        self.fsc.ai_data = {
            "layout": {"name": "direct"},
            "grub": {"reorder_uefi": reorder_uefi},
        }

        await self.fsc.convert_autoinstall_config()
        curtin_cfg = model.render()
        self.assertEqual(reorder_uefi, curtin_cfg["grub"]["reorder_uefi"])

    @mock.patch("subiquity.server.controllers.filesystem.open", mock.mock_open())
    async def test_probe_once_locked_probe_data(self):
        self.fsc._configured = False
        self.fsc.locked_probe_data = True
        self.fsc.queued_probe_data = None
        self.app.prober.get_storage = mock.AsyncMock(return_value={})
        with mock.patch.object(self.fsc.model, "load_probe_data") as load:
            await self.fsc._probe_once(restricted=True)
        self.assertEqual(self.fsc.queued_probe_data, {})
        load.assert_not_called()

    @parameterized.expand(((0,), ("1G",)))
    async def test_layout_plus_swap(self, swapsize):
        self.fsc.model = model = make_model(Bootloader.UEFI)
        self.fsc.run_autoinstall_guided = mock.AsyncMock()

        self.fsc.ai_data = {"layout": {"name": "direct"}, "swap": {"size": swapsize}}

        await self.fsc.convert_autoinstall_config()
        curtin_cfg = model.render()
        self.assertEqual(swapsize, curtin_cfg["swap"]["size"])

    @mock.patch("subiquity.server.controllers.filesystem.open", mock.mock_open())
    async def test_probe_once_unlocked_probe_data(self):
        self.fsc._configured = False
        self.fsc.locked_probe_data = False
        self.fsc.queued_probe_data = None
        self.app.prober.get_storage = mock.AsyncMock(return_value={})
        with mock.patch.object(self.fsc.model, "load_probe_data") as load:
            await self.fsc._probe_once(restricted=True)
        self.assertIsNone(self.fsc.queued_probe_data, {})
        load.assert_called_once_with({})

    async def test_v2_reset_POST_no_queued_data(self):
        self.fsc.queued_probe_data = None
        with mock.patch.object(self.fsc.model, "load_probe_data") as load:
            await self.fsc.v2_reset_POST()
        load.assert_not_called()

    async def test_v2_reset_POST_queued_data(self):
        self.fsc.queued_probe_data = {}
        with mock.patch.object(self.fsc.model, "load_probe_data") as load:
            await self.fsc.v2_reset_POST()
        load.assert_called_once_with({})

    async def test_v2_ensure_transaction_POST(self):
        self.fsc.locked_probe_data = False
        await self.fsc.v2_ensure_transaction_POST()
        self.assertTrue(self.fsc.locked_probe_data)

    async def test_v2_reformat_disk_POST(self):
        self.fsc.locked_probe_data = False
        with mock.patch.object(self.fsc, "reformat") as reformat:
            await self.fsc.v2_reformat_disk_POST(ReformatDisk(disk_id="dev-sda"))
        self.assertTrue(self.fsc.locked_probe_data)
        reformat.assert_called_once()

    @mock.patch(MOCK_PREFIX + "boot.is_boot_device", mock.Mock(return_value=True))
    async def test_v2_add_boot_partition_POST_existing_bootloader(self):
        self.fsc.locked_probe_data = False
        with mock.patch.object(self.fsc, "add_boot_disk") as add_boot_disk:
            with self.assertRaisesRegex(ValueError, r"already\ has\ bootloader"):
                await self.fsc.v2_add_boot_partition_POST("dev-sda")
        self.assertTrue(self.fsc.locked_probe_data)
        add_boot_disk.assert_not_called()

    @mock.patch(MOCK_PREFIX + "boot.is_boot_device", mock.Mock(return_value=False))
    @mock.patch(MOCK_PREFIX + "DeviceAction.supported", mock.Mock(return_value=[]))
    async def test_v2_add_boot_partition_POST_not_supported(self):
        self.fsc.locked_probe_data = False
        with mock.patch.object(self.fsc, "add_boot_disk") as add_boot_disk:
            with self.assertRaisesRegex(ValueError, r"does\ not\ support\ boot"):
                await self.fsc.v2_add_boot_partition_POST("dev-sda")
        self.assertTrue(self.fsc.locked_probe_data)
        add_boot_disk.assert_not_called()

    @mock.patch(MOCK_PREFIX + "boot.is_boot_device", mock.Mock(return_value=False))
    @mock.patch(
        MOCK_PREFIX + "DeviceAction.supported",
        mock.Mock(return_value=[DeviceAction.TOGGLE_BOOT]),
    )
    async def test_v2_add_boot_partition_POST(self):
        self.fsc.locked_probe_data = False
        with mock.patch.object(self.fsc, "add_boot_disk") as add_boot_disk:
            await self.fsc.v2_add_boot_partition_POST("dev-sda")
        self.assertTrue(self.fsc.locked_probe_data)
        add_boot_disk.assert_called_once()

    async def test_v2_add_partition_POST_changing_boot(self):
        self.fsc.locked_probe_data = False
        data = AddPartitionV2(
            disk_id="dev-sda",
            partition=Partition(
                format="ext4",
                mount="/",
                boot=True,
            ),
            gap=Gap(
                offset=1 << 20,
                size=1000 << 20,
                usable=GapUsable.YES,
            ),
        )
        with mock.patch.object(self.fsc, "create_partition") as create_part:
            with self.assertRaisesRegex(
                ValueError, r"does\ not\ support\ changing\ boot"
            ):
                await self.fsc.v2_add_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        create_part.assert_not_called()

    async def test_v2_add_partition_POST_too_large(self):
        self.fsc.locked_probe_data = False
        data = AddPartitionV2(
            disk_id="dev-sda",
            partition=Partition(
                format="ext4",
                mount="/",
                size=2000 << 20,
            ),
            gap=Gap(
                offset=1 << 20,
                size=1000 << 20,
                usable=GapUsable.YES,
            ),
        )
        with mock.patch.object(self.fsc, "create_partition") as create_part:
            with self.assertRaisesRegex(ValueError, r"too\ large"):
                await self.fsc.v2_add_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        create_part.assert_not_called()

    @mock.patch(MOCK_PREFIX + "gaps.at_offset")
    async def test_v2_add_partition_POST(self, at_offset):
        at_offset.split = mock.Mock(return_value=[mock.Mock()])
        self.fsc.locked_probe_data = False
        data = AddPartitionV2(
            disk_id="dev-sda",
            partition=Partition(
                format="ext4",
                mount="/",
            ),
            gap=Gap(
                offset=1 << 20,
                size=1000 << 20,
                usable=GapUsable.YES,
            ),
        )
        with mock.patch.object(self.fsc, "create_partition") as create_part:
            await self.fsc.v2_add_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        create_part.assert_called_once()

    async def test_v2_delete_partition_POST(self):
        self.fsc.locked_probe_data = False
        data = ModifyPartitionV2(
            disk_id="dev-sda",
            partition=Partition(number=1),
        )
        with mock.patch.object(self.fsc, "delete_partition") as del_part:
            with mock.patch.object(self.fsc, "get_partition"):
                await self.fsc.v2_delete_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        del_part.assert_called_once()

    async def test_v2_edit_partition_POST_change_boot(self):
        self.fsc.locked_probe_data = False
        data = ModifyPartitionV2(
            disk_id="dev-sda",
            partition=Partition(number=1, boot=True),
        )
        existing = Partition(number=1, size=1000 << 20, boot=False)
        with mock.patch.object(self.fsc, "partition_disk_handler") as handler:
            with mock.patch.object(self.fsc, "get_partition", return_value=existing):
                with self.assertRaisesRegex(ValueError, r"changing\ boot"):
                    await self.fsc.v2_edit_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        handler.assert_not_called()

    async def test_v2_edit_partition_POST(self):
        self.fsc.locked_probe_data = False
        data = ModifyPartitionV2(
            disk_id="dev-sda",
            partition=Partition(number=1),
        )
        existing = Partition(number=1, size=1000 << 20, boot=False)
        with mock.patch.object(self.fsc, "partition_disk_handler") as handler:
            with mock.patch.object(self.fsc, "get_partition", return_value=existing):
                await self.fsc.v2_edit_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        handler.assert_called_once()


class TestGuided(IsolatedAsyncioTestCase):
    boot_expectations = [
        (Bootloader.UEFI, "gpt", "/boot/efi"),
        (Bootloader.UEFI, "msdos", "/boot/efi"),
        (Bootloader.BIOS, "gpt", None),
        # BIOS + msdos is different
        (Bootloader.PREP, "gpt", None),
        (Bootloader.PREP, "msdos", None),
    ]

    async def _guided_setup(self, bootloader, ptable, storage_version=None):
        self.app = make_app()
        self.app.opts.bootloader = bootloader.value
        self.controller = FilesystemController(self.app)
        self.controller.supports_resilient_boot = True
        self.controller._examine_systems_task.start_sync()
        self.app.dr_cfg = DRConfig()
        self.app.base_model.source.current.variations = {
            "default": CatalogEntryVariation(path="", size=1),
        }
        self.app.controllers.Source.get_handler.return_value = TrivialSourceHandler("")
        await self.controller._examine_systems_task.wait()
        self.model = make_model(bootloader, storage_version)
        self.controller.model = self.model
        self.d1 = make_disk(self.model, ptable=ptable)

    @parameterized.expand(boot_expectations)
    async def test_guided_direct(self, bootloader, ptable, p1mnt):
        await self._guided_setup(bootloader, ptable)
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, allowed=default_capabilities
        )
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.DIRECT)
        )
        [d1p1, d1p2] = self.d1.partitions()
        self.assertEqual(p1mnt, d1p1.mount)
        self.assertEqual("/", d1p2.mount)
        self.assertFalse(d1p1.preserve)
        self.assertFalse(d1p2.preserve)
        self.assertIsNone(gaps.largest_gap(self.d1))

    async def test_guided_reset_partition(self):
        await self._guided_setup(Bootloader.UEFI, "gpt")
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, allowed=default_capabilities
        )
        await self.controller.guided(
            GuidedChoiceV2(
                target=target, capability=GuidedCapability.DIRECT, reset_partition=True
            )
        )
        [d1p1, d1p2, d1p3] = self.d1.partitions()
        self.assertEqual("/boot/efi", d1p1.mount)
        self.assertEqual(None, d1p2.mount)
        self.assertEqual(DRY_RUN_RESET_SIZE, d1p2.size)
        self.assertEqual("/", d1p3.mount)

    async def test_guided_reset_partition_only(self):
        await self._guided_setup(Bootloader.UEFI, "gpt")
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, allowed=default_capabilities
        )
        await self.controller.guided(
            GuidedChoiceV2(
                target=target, capability=GuidedCapability.DIRECT, reset_partition=True
            ),
            reset_partition_only=True,
        )
        [d1p1, d1p2] = self.d1.partitions()
        self.assertEqual(None, d1p1.mount)
        self.assertEqual(None, d1p2.mount)
        self.assertEqual(DRY_RUN_RESET_SIZE, d1p2.size)

    async def test_guided_direct_BIOS_MSDOS(self):
        await self._guided_setup(Bootloader.BIOS, "msdos")
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, allowed=default_capabilities
        )
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.DIRECT)
        )
        [d1p1] = self.d1.partitions()
        self.assertEqual("/", d1p1.mount)
        self.assertFalse(d1p1.preserve)
        self.assertIsNone(gaps.largest_gap(self.d1))

    @parameterized.expand(boot_expectations)
    async def test_guided_lvm(self, bootloader, ptable, p1mnt):
        await self._guided_setup(bootloader, ptable)
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, allowed=default_capabilities
        )
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.LVM)
        )
        [d1p1, d1p2, d1p3] = self.d1.partitions()
        self.assertEqual(p1mnt, d1p1.mount)
        self.assertEqual("/boot", d1p2.mount)
        self.assertEqual(None, d1p3.mount)
        self.assertFalse(d1p1.preserve)
        self.assertFalse(d1p2.preserve)
        self.assertFalse(d1p3.preserve)
        [vg] = self.model._all(type="lvm_volgroup")
        [part] = list(vg.devices)
        self.assertEqual(d1p3, part)
        self.assertIsNone(gaps.largest_gap(self.d1))

    async def test_guided_lvm_BIOS_MSDOS(self):
        await self._guided_setup(Bootloader.BIOS, "msdos")
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, allowed=default_capabilities
        )
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.LVM)
        )
        [d1p1, d1p2] = self.d1.partitions()
        self.assertEqual("/boot", d1p1.mount)
        [vg] = self.model._all(type="lvm_volgroup")
        [part] = list(vg.devices)
        self.assertEqual(d1p2, part)
        self.assertEqual(None, d1p2.mount)
        self.assertFalse(d1p1.preserve)
        self.assertFalse(d1p2.preserve)
        self.assertIsNone(gaps.largest_gap(self.d1))

    @parameterized.expand(boot_expectations)
    async def test_guided_zfs(self, bootloader, ptable, p1mnt):
        await self._guided_setup(bootloader, ptable)
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, allowed=default_capabilities
        )
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.ZFS)
        )
        [d1p1, d1p2, d1p3] = self.d1.partitions()
        self.assertEqual(p1mnt, d1p1.mount)
        self.assertEqual(None, d1p2.mount)
        self.assertEqual(None, d1p3.mount)
        self.assertFalse(d1p1.preserve)
        self.assertFalse(d1p2.preserve)
        self.assertFalse(d1p3.preserve)
        [rpool] = self.model._all(type="zpool", pool="rpool")
        self.assertEqual("/", rpool.path)
        [bpool] = self.model._all(type="zpool", pool="bpool")
        self.assertEqual("/boot", bpool.path)

    async def test_guided_zfs_BIOS_MSDOS(self):
        await self._guided_setup(Bootloader.BIOS, "msdos")
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, allowed=default_capabilities
        )
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.ZFS)
        )
        [d1p1, d1p2] = self.d1.partitions()
        self.assertEqual(None, d1p1.mount)
        self.assertEqual(None, d1p2.mount)
        self.assertFalse(d1p1.preserve)
        self.assertFalse(d1p2.preserve)
        [rpool] = self.model._all(type="zpool", pool="rpool")
        self.assertEqual("/", rpool.path)
        [bpool] = self.model._all(type="zpool", pool="bpool")
        self.assertEqual("/boot", bpool.path)

    async def _guided_side_by_side(self, bl, ptable):
        await self._guided_setup(bl, ptable, storage_version=2)
        self.controller.add_boot_disk(self.d1)
        for p in self.d1._partitions:
            p.preserve = True
            if bl == Bootloader.UEFI:
                # let it pass the is_esp check
                p._info = FakeStorageInfo(size=p.size)
                p._info.raw["ID_PART_ENTRY_TYPE"] = str(0xEF)
        # Make it more interesting with other partitions.
        # Also create the extended part if needed.
        g = gaps.largest_gap(self.d1)
        make_partition(
            self.model, self.d1, preserve=True, size=10 << 30, offset=g.offset
        )
        if ptable == "msdos":
            g = gaps.largest_gap(self.d1)
            make_partition(
                self.model,
                self.d1,
                preserve=True,
                flag="extended",
                size=g.size,
                offset=g.offset,
            )
            g = gaps.largest_gap(self.d1)
            make_partition(
                self.model,
                self.d1,
                preserve=True,
                flag="logical",
                size=10 << 30,
                offset=g.offset,
            )

    @parameterized.expand(
        [
            (bl, pt, flag)
            for bl in list(Bootloader)
            for pt, flag in (("msdos", "logical"), ("gpt", None))
        ]
    )
    async def test_guided_direct_side_by_side(self, bl, pt, flag):
        await self._guided_side_by_side(bl, pt)
        parts_before = self.d1._partitions.copy()
        gap = gaps.largest_gap(self.d1)
        target = GuidedStorageTargetUseGap(
            disk_id=self.d1.id, gap=gap, allowed=default_capabilities
        )
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.DIRECT)
        )
        parts_after = gaps.parts_and_gaps(self.d1)[:-1]
        self.assertEqual(parts_before, parts_after)
        p = gaps.parts_and_gaps(self.d1)[-1]
        self.assertEqual("/", p.mount)
        self.assertEqual(flag, p.flag)

    @parameterized.expand(
        [
            (bl, pt, flag)
            for bl in list(Bootloader)
            for pt, flag in (("msdos", "logical"), ("gpt", None))
        ]
    )
    async def test_guided_lvm_side_by_side(self, bl, pt, flag):
        await self._guided_side_by_side(bl, pt)
        parts_before = self.d1._partitions.copy()
        gap = gaps.largest_gap(self.d1)
        target = GuidedStorageTargetUseGap(
            disk_id=self.d1.id, gap=gap, allowed=default_capabilities
        )
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.LVM)
        )
        parts_after = gaps.parts_and_gaps(self.d1)[:-2]
        self.assertEqual(parts_before, parts_after)
        p_boot, p_data = gaps.parts_and_gaps(self.d1)[-2:]
        self.assertEqual("/boot", p_boot.mount)
        self.assertEqual(flag, p_boot.flag)
        self.assertEqual(None, p_data.mount)
        self.assertEqual(flag, p_data.flag)


class TestLayout(IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.opts.bootloader = None
        self.fsc = FilesystemController(app=self.app)

    @parameterized.expand([("reformat_disk",), ("use_gap",)])
    async def test_good_modes(self, mode):
        self.fsc.validate_layout_mode(mode)

    @parameterized.expand([("resize_biggest",), ("use_free",)])
    async def test_bad_modes(self, mode):
        with self.assertRaises(ValueError):
            self.fsc.validate_layout_mode(mode)


class TestGuidedV2(IsolatedAsyncioTestCase):
    async def _setup(self, bootloader, ptable, fix_bios=True, **kw):
        self.app = make_app()
        self.app.opts.bootloader = bootloader.value
        self.fsc = FilesystemController(app=self.app)
        self.fsc.calculate_suggested_install_min = mock.Mock()
        self.fsc.calculate_suggested_install_min.return_value = 10 << 30
        self.fsc.model = self.model = make_model(bootloader)
        self.fsc._examine_systems_task.start_sync()
        self.app.dr_cfg = DRConfig()
        self.app.base_model.source.current.variations = {
            "default": CatalogEntryVariation(path="", size=1),
        }
        self.app.controllers.Source.get_handler.return_value = TrivialSourceHandler("")
        await self.fsc._examine_systems_task.wait()
        self.disk = make_disk(self.model, ptable=ptable, **kw)
        self.model.storage_version = 2
        self.fs_probe = {}
        self.fsc.model._probe_data = {
            "blockdev": {},
            "filesystem": self.fs_probe,
        }
        self.fsc._probe_task.task = mock.Mock()
        self.fsc._examine_systems_task.task = mock.Mock()
        if bootloader == Bootloader.BIOS and ptable != "msdos" and fix_bios:
            make_partition(
                self.model,
                self.disk,
                preserve=True,
                flag="bios_grub",
                size=1 << 20,
                offset=1 << 20,
            )

    @parameterized.expand(bootloaders_and_ptables)
    async def test_blank_disk(self, bootloader, ptable):
        # blank disks should not report a UseGap case
        await self._setup(bootloader, ptable, fix_bios=False)
        expected = [
            GuidedStorageTargetReformat(
                disk_id=self.disk.id, allowed=default_capabilities
            ),
            GuidedStorageTargetManual(),
        ]
        resp = await self.fsc.v2_guided_GET()
        self.assertEqual(expected, resp.targets)
        self.assertEqual(ProbeStatus.DONE, resp.status)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_probing(self, bootloader, ptable):
        await self._setup(bootloader, ptable, fix_bios=False)
        self.fsc._probe_task.task = None
        resp = await self.fsc.v2_guided_GET()
        self.assertEqual([], resp.targets)
        self.assertEqual(ProbeStatus.PROBING, resp.status)

    async def test_manual(self):
        await self._setup(Bootloader.UEFI, "gpt")
        guided_get_resp = await self.fsc.v2_guided_GET()
        [reformat, manual] = guided_get_resp.targets
        self.assertEqual(manual, GuidedStorageTargetManual())
        data = GuidedChoiceV2(target=reformat, capability=manual.allowed[0])
        # POSTing the manual choice doesn't change anything
        await self.fsc.v2_guided_POST(data=data)
        guided_get_resp = await self.fsc.v2_guided_GET()
        self.assertEqual([reformat, manual], guided_get_resp.targets)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_small_blank_disk(self, bootloader, ptable):
        await self._setup(bootloader, ptable, size=1 << 30)
        resp = await self.fsc.v2_guided_GET()
        expected = [
            GuidedStorageTargetReformat(
                disk_id=self.disk.id,
                allowed=[],
                disallowed=default_capabilities_disallowed_too_small,
            ),
            GuidedStorageTargetManual(),
        ]
        self.assertEqual(expected, resp.targets)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_used_half_disk(self, bootloader, ptable):
        await self._setup(bootloader, ptable, size=100 << 30)
        p = make_partition(self.model, self.disk, preserve=True, size=50 << 30)
        gap_offset = p.size + p.offset
        self.fs_probe[p._path()] = {"ESTIMATED_MIN_SIZE": 1 << 20}
        resp = await self.fsc.v2_guided_GET()

        reformat = resp.targets.pop(0)
        self.assertEqual(
            GuidedStorageTargetReformat(
                disk_id=self.disk.id, allowed=default_capabilities
            ),
            reformat,
        )

        use_gap = resp.targets.pop(0)
        self.assertEqual(self.disk.id, use_gap.disk_id)
        self.assertEqual(gap_offset, use_gap.gap.offset)

        resize = resp.targets.pop(0)
        self.assertEqual(self.disk.id, resize.disk_id)
        self.assertEqual(p.number, resize.partition_number)
        self.assertTrue(isinstance(resize, GuidedStorageTargetResize))
        self.assertEqual(1, len(resp.targets))

    @parameterized.expand(bootloaders_and_ptables)
    async def test_used_full_disk(self, bootloader, ptable):
        await self._setup(bootloader, ptable)
        p = make_partition(
            self.model, self.disk, preserve=True, size=gaps.largest_gap_size(self.disk)
        )
        self.fs_probe[p._path()] = {"ESTIMATED_MIN_SIZE": 1 << 20}
        resp = await self.fsc.v2_guided_GET()
        reformat = resp.targets.pop(0)
        self.assertEqual(
            GuidedStorageTargetReformat(
                disk_id=self.disk.id, allowed=default_capabilities
            ),
            reformat,
        )

        resize = resp.targets.pop(0)
        self.assertEqual(self.disk.id, resize.disk_id)
        self.assertEqual(p.number, resize.partition_number)
        self.assertTrue(isinstance(resize, GuidedStorageTargetResize))
        self.assertEqual(1, len(resp.targets))

    @parameterized.expand(bootloaders_and_ptables)
    async def test_weighted_split(self, bootloader, ptable):
        await self._setup(bootloader, ptable, size=250 << 30)
        # add an extra, filler, partition so that there is no use_gap result
        make_partition(self.model, self.disk, preserve=True, size=9 << 30)
        p = make_partition(self.model, self.disk, preserve=True, size=240 << 30)
        self.fs_probe[p._path()] = {"ESTIMATED_MIN_SIZE": 40 << 30}
        self.fsc.calculate_suggested_install_min.return_value = 10 << 30
        resp = await self.fsc.v2_guided_GET()
        possible = [t for t in resp.targets if t.allowed]
        reformat = possible.pop(0)
        self.assertEqual(
            GuidedStorageTargetReformat(
                disk_id=self.disk.id, allowed=default_capabilities
            ),
            reformat,
        )

        resize = possible.pop(0)
        expected = GuidedStorageTargetResize(
            disk_id=self.disk.id,
            partition_number=p.number,
            new_size=200 << 30,
            minimum=50 << 30,
            recommended=200 << 30,
            maximum=230 << 30,
            allowed=default_capabilities,
        )
        self.assertEqual(expected, resize)
        self.assertEqual(1, len(possible))

    @parameterized.expand(bootloaders_and_ptables)
    async def test_half_disk_reformat(self, bootloader, ptable):
        await self._setup(bootloader, ptable, size=100 << 30)
        p = make_partition(self.model, self.disk, preserve=True, size=50 << 30)
        self.fs_probe[p._path()] = {"ESTIMATED_MIN_SIZE": 1 << 20}

        guided_get_resp = await self.fsc.v2_guided_GET()
        reformat = guided_get_resp.targets.pop(0)
        self.assertTrue(isinstance(reformat, GuidedStorageTargetReformat))

        use_gap = guided_get_resp.targets.pop(0)
        self.assertTrue(isinstance(use_gap, GuidedStorageTargetUseGap))

        resize = guided_get_resp.targets.pop(0)
        self.assertTrue(isinstance(resize, GuidedStorageTargetResize))

        data = GuidedChoiceV2(target=reformat, capability=GuidedCapability.DIRECT)
        expected_config = copy.copy(data)
        resp = await self.fsc.v2_guided_POST(data=data)
        self.assertEqual(expected_config, resp.configured)

        resp = await self.fsc.v2_GET()
        self.assertFalse(resp.need_root)
        self.assertFalse(resp.need_boot)
        self.assertEqual(1, len(guided_get_resp.targets))

    @parameterized.expand(bootloaders_and_ptables)
    async def test_half_disk_use_gap(self, bootloader, ptable):
        await self._setup(bootloader, ptable, size=100 << 30)
        p = make_partition(self.model, self.disk, preserve=True, size=50 << 30)
        self.fs_probe[p._path()] = {"ESTIMATED_MIN_SIZE": 1 << 20}

        resp = await self.fsc.v2_GET()
        [orig_p, g] = resp.disks[0].partitions[-2:]

        guided_get_resp = await self.fsc.v2_guided_GET()
        reformat = guided_get_resp.targets.pop(0)
        self.assertTrue(isinstance(reformat, GuidedStorageTargetReformat))

        use_gap = guided_get_resp.targets.pop(0)
        self.assertTrue(isinstance(use_gap, GuidedStorageTargetUseGap))
        self.assertEqual(g, use_gap.gap)
        data = GuidedChoiceV2(target=use_gap, capability=GuidedCapability.DIRECT)
        expected_config = copy.copy(data)
        resp = await self.fsc.v2_guided_POST(data=data)
        self.assertEqual(expected_config, resp.configured)

        resize = guided_get_resp.targets.pop(0)
        self.assertTrue(isinstance(resize, GuidedStorageTargetResize))

        resp = await self.fsc.v2_GET()
        existing_part = [
            p
            for p in resp.disks[0].partitions
            if getattr(p, "number", None) == orig_p.number
        ][0]
        self.assertEqual(orig_p, existing_part)
        self.assertFalse(resp.need_root)
        self.assertFalse(resp.need_boot)
        self.assertEqual(1, len(guided_get_resp.targets))

    @parameterized.expand(bootloaders_and_ptables)
    async def test_half_disk_resize(self, bootloader, ptable):
        await self._setup(bootloader, ptable, size=100 << 30)
        p = make_partition(self.model, self.disk, preserve=True, size=50 << 30)
        self.fs_probe[p._path()] = {"ESTIMATED_MIN_SIZE": 1 << 20}

        resp = await self.fsc.v2_GET()
        [orig_p, g] = resp.disks[0].partitions[-2:]

        guided_get_resp = await self.fsc.v2_guided_GET()
        reformat = guided_get_resp.targets.pop(0)
        self.assertTrue(isinstance(reformat, GuidedStorageTargetReformat))

        use_gap = guided_get_resp.targets.pop(0)
        self.assertTrue(isinstance(use_gap, GuidedStorageTargetUseGap))

        resize = guided_get_resp.targets.pop(0)
        self.assertTrue(isinstance(resize, GuidedStorageTargetResize))
        p_expected = copy.copy(orig_p)
        p_expected.size = resize.new_size = 20 << 30
        p_expected.resize = True
        data = GuidedChoiceV2(target=resize, capability=GuidedCapability.DIRECT)
        expected_config = copy.copy(data)
        resp = await self.fsc.v2_guided_POST(data=data)
        self.assertEqual(expected_config, resp.configured)

        resp = await self.fsc.v2_GET()
        existing_part = [
            p
            for p in resp.disks[0].partitions
            if getattr(p, "number", None) == orig_p.number
        ][0]
        self.assertEqual(p_expected, existing_part)
        self.assertFalse(resp.need_root)
        self.assertFalse(resp.need_boot)
        self.assertEqual(1, len(guided_get_resp.targets))

    @parameterized.expand(
        [
            [10],
            [20],
            [25],
            [30],
            [50],
            [100],
            [250],
            [1000],
            [1024],
        ]
    )
    async def test_lvm_20G_bad_offset(self, disk_size):
        disk_size = disk_size << 30
        await self._setup(Bootloader.BIOS, "gpt", size=disk_size)

        guided_get_resp = await self.fsc.v2_guided_GET()

        reformat = guided_get_resp.targets.pop(0)
        self.assertTrue(isinstance(reformat, GuidedStorageTargetReformat))

        data = GuidedChoiceV2(target=reformat, capability=GuidedCapability.LVM)

        expected_config = copy.copy(data)
        resp = await self.fsc.v2_guided_POST(data=data)
        self.assertEqual(expected_config, resp.configured)

        resp = await self.fsc.v2_GET()
        parts = resp.disks[0].partitions

        for p in parts:
            self.assertEqual(0, p.offset % (1 << 20), p)
            self.assertEqual(0, p.size % (1 << 20), p)

        for i in range(len(parts) - 1):
            self.assertEqual(parts[i + 1].offset, parts[i].offset + parts[i].size)
        self.assertEqual(
            disk_size - (1 << 20), parts[-1].offset + parts[-1].size, disk_size
        )

    async def _sizing_setup(self, bootloader, ptable, disk_size, policy):
        await self._setup(bootloader, ptable, size=disk_size)

        resp = await self.fsc.v2_guided_GET()
        reformat = [
            target
            for target in resp.targets
            if isinstance(target, GuidedStorageTargetReformat)
        ][0]
        data = GuidedChoiceV2(
            target=reformat, capability=GuidedCapability.LVM, sizing_policy=policy
        )
        await self.fsc.v2_guided_POST(data=data)
        resp = await self.fsc.GET()

        [vg] = matching_dicts(resp.config, type="lvm_volgroup")
        [part_id] = vg["devices"]
        [part] = matching_dicts(resp.config, id=part_id)
        part_size = part["size"]  # already an int
        [lvm_partition] = matching_dicts(resp.config, type="lvm_partition")
        size = dehumanize_size(lvm_partition["size"])
        return size, part_size

    @parameterized.expand(bootloaders_and_ptables)
    async def test_scaled_disk(self, bootloader, ptable):
        size, part_size = await self._sizing_setup(
            bootloader, ptable, 50 << 30, SizingPolicy.SCALED
        )
        # expected to be about half, differing by boot and ptable types
        self.assertLess(20 << 30, size)
        self.assertLess(size, 30 << 30)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_unscaled_disk(self, bootloader, ptable):
        size, part_size = await self._sizing_setup(
            bootloader, ptable, 50 << 30, SizingPolicy.ALL
        )
        # there is some subtle differences in sizing depending on
        # ptable/bootloader and how the rounding goes
        self.assertLess(part_size - (5 << 20), size)
        self.assertLess(size, part_size)
        # but we should using most of the disk, minus boot partition(s)
        self.assertLess(45 << 30, size)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_in_use(self, bootloader, ptable):
        # Disks with "in use" partitions allow a reformat if there is
        # enough space on the rest of the disk.
        await self._setup(bootloader, ptable, fix_bios=True)
        make_partition(
            self.model, self.disk, preserve=True, size=4 << 30, is_in_use=True
        )
        expected = [
            GuidedStorageTargetReformat(
                disk_id=self.disk.id, allowed=default_capabilities
            ),
            GuidedStorageTargetManual(),
        ]
        resp = await self.fsc.v2_guided_GET()
        self.assertEqual(expected, resp.targets)
        self.assertEqual(ProbeStatus.DONE, resp.status)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_in_use_full(self, bootloader, ptable):
        # Disks with "in use" partitions allow a reformat (but not
        # usegap) if there is enough space on the rest of the disk,
        # even if the disk is full of other partitions.
        await self._setup(bootloader, ptable, fix_bios=True)
        make_partition(
            self.model, self.disk, preserve=True, size=4 << 30, is_in_use=True
        )
        make_partition(
            self.model, self.disk, preserve=True, size=gaps.largest_gap_size(self.disk)
        )
        expected = [
            GuidedStorageTargetReformat(
                disk_id=self.disk.id, allowed=default_capabilities
            ),
            GuidedStorageTargetManual(),
        ]
        resp = await self.fsc.v2_guided_GET()
        self.assertEqual(expected, resp.targets)
        self.assertEqual(ProbeStatus.DONE, resp.status)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_in_use_too_small(self, bootloader, ptable):
        # Disks with "in use" partitions do not allow a reformat if
        # there is not enough space on the rest of the disk.
        await self._setup(bootloader, ptable, fix_bios=True, size=25 << 30)
        print(bootloader, ptable)
        make_partition(
            self.model, self.disk, preserve=True, size=23 << 30, is_in_use=True
        )
        make_partition(
            self.model, self.disk, preserve=True, size=gaps.largest_gap_size(self.disk)
        )
        resp = await self.fsc.v2_guided_GET()
        expected = [
            GuidedStorageTargetReformat(
                disk_id=self.disk.id,
                allowed=[],
                disallowed=default_capabilities_disallowed_too_small,
            ),
            GuidedStorageTargetManual(),
        ]
        self.assertEqual(expected, resp.targets)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_in_use_reformat_and_gap(self, bootloader, ptable):
        # Disks with "in use" partitions allow both a reformat and a
        # usegap if there is an in use partition, another partition
        # and a big enough gap.
        await self._setup(bootloader, ptable, fix_bios=True)
        make_partition(
            self.model, self.disk, preserve=True, size=4 << 30, is_in_use=True
        )
        make_partition(
            self.model,
            self.disk,
            preserve=True,
            size=gaps.largest_gap_size(self.disk) // 2,
        )
        expected = [
            GuidedStorageTargetReformat(
                disk_id=self.disk.id, allowed=default_capabilities
            ),
            GuidedStorageTargetUseGap(
                disk_id=self.disk.id,
                allowed=default_capabilities,
                gap=labels.for_client(gaps.largest_gap(self.disk)),
            ),
            GuidedStorageTargetManual(),
        ]
        resp = await self.fsc.v2_guided_GET()
        self.assertEqual(expected, resp.targets)
        self.assertEqual(ProbeStatus.DONE, resp.status)


class TestManualBoot(IsolatedAsyncioTestCase):
    def _setup(self, bootloader, ptable, **kw):
        self.app = make_app()
        self.app.opts.bootloader = bootloader.value
        self.fsc = FilesystemController(app=self.app)
        self.fsc.calculate_suggested_install_min = mock.Mock()
        self.fsc.calculate_suggested_install_min.return_value = 10 << 30
        self.fsc.model = self.model = make_model(bootloader)
        self.model.storage_version = 2
        self.fsc._probe_task.task = mock.Mock()
        self.fsc._examine_systems_task.task = mock.Mock()

    @parameterized.expand(bootloaders_and_ptables)
    async def test_get_boot_disks_only(self, bootloader, ptable):
        self._setup(bootloader, ptable)
        make_disk(self.model)
        resp = await self.fsc.v2_GET()
        [d] = resp.disks
        self.assertTrue(d.can_be_boot_device)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_get_boot_disks_all(self, bootloader, ptable):
        self._setup(bootloader, ptable)
        make_disk(self.model)
        make_disk(self.model)
        resp = await self.fsc.v2_GET()
        [d1, d2] = resp.disks
        self.assertTrue(d1.can_be_boot_device)
        self.assertTrue(d2.can_be_boot_device)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_get_boot_disks_some(self, bootloader, ptable):
        self._setup(bootloader, ptable)
        d1 = make_disk(self.model)
        d2 = make_disk(self.model)
        make_partition(self.model, d1, size=gaps.largest_gap_size(d1), preserve=True)
        if bootloader == Bootloader.NONE:
            # NONE will always pass the boot check, even on a full disk
            bootable = set([d1.id, d2.id])
        else:
            bootable = set([d2.id])
        resp = await self.fsc.v2_GET()
        for d in resp.disks:
            self.assertEqual(d.id in bootable, d.can_be_boot_device)


class TestCoreBootInstallMethods(IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.command_runner = mock.AsyncMock()
        self.app.opts.bootloader = "UEFI"
        self.app.report_start_event = mock.Mock()
        self.app.report_finish_event = mock.Mock()
        self.app.prober = mock.Mock()
        self.app.prober.get_storage = mock.AsyncMock()
        self.app.snapdapi = snapdapi.make_api_client(AsyncSnapd(get_fake_connection()))
        self.app.dr_cfg = DRConfig()
        self.app.dr_cfg.systems_dir_exists = True
        self.app.controllers.Source.get_handler.return_value = TrivialSourceHandler("")
        self.fsc = FilesystemController(app=self.app)
        self.fsc._configured = True
        self.fsc.model = make_model(Bootloader.UEFI)
        self.fsc._mount_systems_dir = mock.AsyncMock()

    def _add_details_for_structures(self, structures):
        self.fsc._info = VariationInfo(
            name="foo",
            label="system",
            system=snapdapi.SystemDetails(
                volumes={
                    "pc": snapdapi.Volume(schema="gpt", structure=structures),
                }
            ),
        )

    async def test_guided_core_boot(self):
        disk = make_disk(self.fsc.model)
        arbitrary_uuid = str(uuid.uuid4())
        self._add_details_for_structures(
            [
                snapdapi.VolumeStructure(
                    type="83,0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    offset=1 << 20,
                    size=1 << 30,
                    filesystem="ext4",
                    name="one",
                ),
                snapdapi.VolumeStructure(
                    type=arbitrary_uuid, offset=2 << 30, size=1 << 30, filesystem="ext4"
                ),
            ]
        )
        await self.fsc.guided_core_boot(disk)
        [part1, part2] = disk.partitions()
        self.assertEqual(part1.offset, 1 << 20)
        self.assertEqual(part1.size, 1 << 30)
        self.assertEqual(part1.fs().fstype, "ext4")
        self.assertEqual(part1.flag, "linux")
        self.assertEqual(part1.partition_name, "one")
        self.assertEqual(part1.partition_type, "0FC63DAF-8483-4772-8E79-3D69D8477DE4")
        self.assertEqual(part2.flag, None)
        self.assertEqual(part2.partition_type, arbitrary_uuid)

    async def test_guided_core_boot_reuse(self):
        disk = make_disk(self.fsc.model)
        # Add a partition that matches one in the volume structure
        reused_part = make_partition(
            self.fsc.model, disk, offset=1 << 20, size=1 << 30, preserve=True
        )
        self.fsc.model.add_filesystem(reused_part, "ext4")
        # And two that do not.
        make_partition(
            self.fsc.model, disk, offset=2 << 30, size=1 << 30, preserve=True
        )
        make_partition(
            self.fsc.model, disk, offset=3 << 30, size=1 << 30, preserve=True
        )
        self._add_details_for_structures(
            [
                snapdapi.VolumeStructure(
                    type="0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    offset=1 << 20,
                    size=1 << 30,
                    filesystem="ext4",
                ),
            ]
        )
        await self.fsc.guided_core_boot(disk)
        [part] = disk.partitions()
        self.assertEqual(reused_part, part)
        self.assertEqual(reused_part.wipe, "superblock")
        self.assertEqual(part.fs().fstype, "ext4")

    async def test_guided_core_boot_reuse_no_format(self):
        disk = make_disk(self.fsc.model)
        existing_part = make_partition(
            self.fsc.model, disk, offset=1 << 20, size=1 << 30, preserve=True
        )
        self._add_details_for_structures(
            [
                snapdapi.VolumeStructure(
                    type="0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    offset=1 << 20,
                    size=1 << 30,
                    filesystem=None,
                ),
            ]
        )
        await self.fsc.guided_core_boot(disk)
        [part] = disk.partitions()
        self.assertEqual(existing_part, part)
        self.assertEqual(existing_part.wipe, None)

    async def test_guided_core_boot_system_data(self):
        disk = make_disk(self.fsc.model)
        self._add_details_for_structures(
            [
                snapdapi.VolumeStructure(
                    type="21686148-6449-6E6F-744E-656564454649",
                    offset=1 << 20,
                    name="BIOS Boot",
                    size=1 << 20,
                    role="",
                    filesystem="",
                ),
                snapdapi.VolumeStructure(
                    type="0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    offset=2 << 20,
                    name="ptname",
                    size=2 << 30,
                    role=snapdapi.Role.SYSTEM_DATA,
                    filesystem="ext4",
                ),
            ]
        )
        await self.fsc.guided_core_boot(disk)
        [bios_part, part] = disk.partitions()
        self.assertEqual(part.offset, 2 << 20)
        self.assertEqual(part.partition_name, "ptname")
        self.assertEqual(part.flag, "linux")
        self.assertEqual(
            part.size, disk.size - (2 << 20) - disk.alignment_data().min_end_offset
        )
        self.assertEqual(part.fs().fstype, "ext4")
        self.assertEqual(part.fs().mount().path, "/")
        self.assertEqual(part.wipe, "superblock")

    async def test_from_sample_data(self):
        # calling this a unit test is definitely questionable. but it
        # runs much more quickly than the integration test!
        self.fsc.model = model = make_model(Bootloader.UEFI)
        disk = make_disk(model)
        self.app.base_model.source.current.variations = {
            "default": CatalogEntryVariation(
                path="", size=1, snapd_system_label="prefer-encrypted"
            ),
        }

        self.app.dr_cfg.systems_dir_exists = True

        await self.fsc._examine_systems_task.start()
        self.fsc.start()

        response = await self.fsc.v2_guided_GET(wait=True)

        self.assertEqual(len(response.targets), 1)
        choice = GuidedChoiceV2(
            target=response.targets[0], capability=GuidedCapability.CORE_BOOT_ENCRYPTED
        )
        await self.fsc.v2_guided_POST(choice)

        self.assertEqual(model.storage_version, 2)

        partition_count = len(
            [
                structure
                for structure in self.fsc._info.system.volumes["pc"].structure
                if structure.role != snapdapi.Role.MBR
            ]
        )
        self.assertEqual(partition_count, len(disk.partitions()))
        mounts = {m.path: m.device.volume for m in model._all(type="mount")}
        self.assertEqual(set(mounts.keys()), {"/", "/boot", "/boot/efi"})
        device_map = {p.id: random_string() for p in disk.partitions()}
        self.fsc.update_devices(device_map)

        with mock.patch.object(
            snapdapi, "post_and_wait", new_callable=mock.AsyncMock
        ) as mocked:
            mocked.return_value = {
                "encrypted-devices": {
                    snapdapi.Role.SYSTEM_DATA: "enc-system-data",
                },
            }
            await self.fsc.setup_encryption(context=self.fsc.context)

        # setup_encryption mutates the filesystem model objects to
        # reference the newly created encrypted objects so re-read the
        # mount to device mapping.
        mounts = {m.path: m.device.volume for m in model._all(type="mount")}
        self.assertEqual(mounts["/"].path, "enc-system-data")

        with mock.patch.object(
            snapdapi, "post_and_wait", new_callable=mock.AsyncMock
        ) as mocked:
            await self.fsc.finish_install(context=self.fsc.context)
        mocked.assert_called_once()
        [call] = mocked.mock_calls
        request = call.args[2]
        self.assertEqual(request.action, snapdapi.SystemAction.INSTALL)
        self.assertEqual(request.step, snapdapi.SystemActionStep.FINISH)

    async def test_from_sample_data_autoinstall(self):
        # calling this a unit test is definitely questionable. but it
        # runs much more quickly than the integration test!
        self.fsc.model = model = make_model(Bootloader.UEFI)
        disk = make_disk(model)
        self.app.base_model.source.current.variations = {
            "default": CatalogEntryVariation(
                path="", size=1, snapd_system_label="prefer-encrypted"
            ),
        }

        self.app.dr_cfg.systems_dir_exists = True

        await self.fsc._examine_systems_task.start()
        await self.fsc._examine_systems_task.wait()
        self.fsc.start()

        await self.fsc.run_autoinstall_guided({"name": "hybrid"})

        self.assertEqual(model.storage_version, 2)

        partition_count = len(
            [
                structure
                for structure in self.fsc._info.system.volumes["pc"].structure
                if structure.role != snapdapi.Role.MBR
            ]
        )
        self.assertEqual(partition_count, len(disk.partitions()))

    async def test_from_sample_data_defective(self):
        self.fsc.model = model = make_model(Bootloader.UEFI)
        make_disk(model)
        self.app.base_model.source.current.variations = {
            "default": CatalogEntryVariation(
                path="", size=1, snapd_system_label="defective"
            ),
        }
        self.app.dr_cfg.systems_dir_exists = True
        await self.fsc._examine_systems_task.start()
        self.fsc.start()
        response = await self.fsc.v2_guided_GET(wait=True)
        self.assertEqual(len(response.targets), 1)
        self.assertEqual(len(response.targets[0].allowed), 0)
        self.assertEqual(len(response.targets[0].disallowed), 1)
        disallowed = response.targets[0].disallowed[0]
        self.assertEqual(
            disallowed.reason,
            GuidedDisallowedCapabilityReason.CORE_BOOT_ENCRYPTION_UNAVAILABLE,
        )
