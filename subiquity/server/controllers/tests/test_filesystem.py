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

import contextlib
import copy
import subprocess
import uuid
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase, mock

import attrs
import jsonschema
import requests
import requests_mock
from curtin.commands.extract import TrivialSourceHandler
from jsonschema.validators import validator_for

from subiquity.common.filesystem import boot, gaps, labels
from subiquity.common.filesystem.actions import DeviceAction
from subiquity.common.types.storage import (
    AddPartitionV2,
    Bootloader,
    CalculateEntropyRequest,
    CoreBootEncryptionFeatures,
    EntropyResponse,
    Gap,
    GapUsable,
    GuidedCapability,
    GuidedChoiceV2,
    GuidedDisallowedCapability,
    GuidedDisallowedCapabilityReason,
    GuidedStorageTargetEraseInstall,
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
    make_model_and_disk,
    make_model_and_lv,
    make_model_and_raid,
    make_model_and_vg,
    make_nvme_controller,
    make_partition,
    make_raid,
)
from subiquity.server.autoinstall import AutoinstallError
from subiquity.server.controllers.filesystem import (
    DRY_RUN_RESET_SIZE,
    FilesystemController,
    StorageConstraintViolationError,
    StorageInvalidUsageError,
    StorageNotFoundError,
    VariationInfo,
    validate_pin_pass,
)
from subiquity.server.dryrun import DRConfig
from subiquity.server.snapd import api as snapdapi
from subiquity.server.snapd import types as snapdtypes
from subiquity.server.snapd.info import SnapdInfo
from subiquity.server.snapd.system_getter import SystemGetter
from subiquity.server.snapd.types import VolumesAuth, VolumesAuthMode
from subiquitycore.snapd import AsyncSnapd, SnapdConnection, get_fake_connection
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
    GuidedCapability.ZFS_LUKS_KEYSTORE,
]


default_capabilities_disallowed_too_small = [
    GuidedDisallowedCapability(
        capability=cap, reason=GuidedDisallowedCapabilityReason.TOO_SMALL
    )
    for cap in default_capabilities
]


class TestValidatePinPass(TestCase):
    def test_valid_pin(self):
        validate_pin_pass(
            passphrase_allowed=False, pin_allowed=True, passphrase=None, pin="1234"
        )

    def test_invalid_pin(self):
        with self.assertRaises(
            StorageInvalidUsageError, msg="pin is a string of digits"
        ):
            validate_pin_pass(
                passphrase_allowed=False, pin_allowed=True, passphrase=None, pin="abcd"
            )

    def test_valid_passphrase(self):
        validate_pin_pass(
            passphrase_allowed=True, pin_allowed=False, passphrase="abcd", pin=None
        )

    def test_unexpected_passphrase(self):
        with self.assertRaises(
            StorageInvalidUsageError, msg="unexpected passphrase supplied"
        ):
            validate_pin_pass(
                passphrase_allowed=False, pin_allowed=False, passphrase="abcd", pin=None
            )

    def test_unexpected_pin(self):
        with self.assertRaises(StorageInvalidUsageError, msg="unexpected pin supplied"):
            validate_pin_pass(
                passphrase_allowed=False, pin_allowed=False, passphrase=None, pin="1234"
            )

    def test_pin_and_pass_supplied(self):
        with self.assertRaises(
            StorageInvalidUsageError,
            msg="must supply at most one of pin and passphrase",
        ):
            validate_pin_pass(
                passphrase_allowed=True, pin_allowed=True, passphrase="abcd", pin="1234"
            )


class TestSubiquityControllerFilesystem(IsolatedAsyncioTestCase):
    MOCK_PREFIX = "subiquity.server.controllers.filesystem."

    def setUp(self):
        self.app = make_app()
        self.app.opts.bootloader = "UEFI"
        self.app.command_runner = mock.AsyncMock()
        self.app.prober = mock.AsyncMock()
        self.app.prober.get_storage = mock.AsyncMock()
        self.app.block_log_dir = "/inexistent"
        self.app.note_file_for_apport = mock.Mock()
        self.app.snapdinfo = mock.Mock(spec=SnapdInfo)
        self.fsc = FilesystemController(app=self.app)
        self.fsc._configured = True

    async def test_probe_restricted(self):
        await self.fsc._probe_once(context=None, restricted=True)
        expected = {"blockdev", "filesystem", "nvme"}
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

    fw_lenovo = {
        "bios-vendor": "LENOVO",
        "bios-version": "R10ET39W (1.24 )",
        "bios-release-date": "08/12/2019",
    }
    fw_edk2_timberland = {
        "bios-vendor": "EFI Development Kit II / OVMF",
        "bios-version": "0.0.0",
        "bios-release-date": "02/06/2015",
    }

    @parameterized.expand(
        (
            (False, fw_lenovo, False),
            (False, fw_edk2_timberland, True),
            (True, fw_lenovo, True),
            (True, fw_edk2_timberland, True),
        )
    )
    async def test_firmware_supports_nvmeotcp_boot(
        self, nbft_exists: bool, firmware: dict[str, str], expected: bool
    ):
        with mock.patch("pathlib.Path.exists", return_value=nbft_exists):
            self.assertEqual(
                expected, self.fsc.firmware_supports_nvmeotcp_boot(firmware)
            )

    @parameterized.expand(
        (
            (False, True, True),
            (False, False, False),
            (False, None, False),
            (True, True, False),
            (True, False, True),
            (True, None, False),
        )
    )
    async def test__probe_firmware(
        self,
        fw_supports: bool,
        opt_supports: bool | None,
        expect_log: bool,
    ):
        self.fsc.model.opt_supports_nvme_tcp_booting = opt_supports
        with mock.patch.object(self.app.prober, "get_firmware", return_value=None):
            with mock.patch.object(
                self.fsc, "firmware_supports_nvmeotcp_boot", return_value=fw_supports
            ):
                with self.assertLogs(
                    "subiquity.server.controllers.filesystem", level="DEBUG"
                ) as debug:
                    await self.fsc._probe_firmware()
        self.assertEqual(fw_supports, self.fsc.model.detected_supports_nvme_tcp_booting)
        found_log = "but CLI argument states otherwise, so ignoring" in [
            record.msg for record in debug.records
        ]
        self.assertEqual(expect_log, found_log)

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
            with self.assertRaises(
                StorageConstraintViolationError, msg="device already has bootloader"
            ):
                await self.fsc.v2_add_boot_partition_POST("dev-sda")
        self.assertTrue(self.fsc.locked_probe_data)
        add_boot_disk.assert_not_called()

    @mock.patch(MOCK_PREFIX + "boot.is_boot_device", mock.Mock(return_value=False))
    @mock.patch(MOCK_PREFIX + "DeviceAction.supported", mock.Mock(return_value=[]))
    async def test_v2_add_boot_partition_POST_not_supported(self):
        self.fsc.locked_probe_data = False
        with mock.patch.object(self.fsc, "add_boot_disk") as add_boot_disk:
            with self.assertRaises(
                StorageConstraintViolationError, msg="disk does not support boot"
            ):
                await self.fsc.v2_add_boot_partition_POST("dev-sda")
        self.assertTrue(self.fsc.locked_probe_data)
        add_boot_disk.assert_not_called()

    async def test_v2_add_boot_partition_POST_unsupported_ptable(self):
        self.fsc.locked_probe_data = False
        self.fsc.model, d = make_model_and_disk(ptable="unsupported")

        with mock.patch.object(self.fsc, "add_boot_disk") as add_boot_disk:
            with self.assertRaisesRegex(
                StorageInvalidUsageError, "unsupported partition table"
            ):
                await self.fsc.v2_add_boot_partition_POST(d.id)
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
                StorageInvalidUsageError, r"does\ not\ support\ changing\ boot"
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
            with self.assertRaisesRegex(StorageConstraintViolationError, r"too\ large"):
                await self.fsc.v2_add_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        create_part.assert_not_called()

    async def test_v2_add_partition_POST_change_pname(self):
        self.fsc.locked_probe_data = False
        data = AddPartitionV2(
            disk_id="dev-sda",
            partition=Partition(
                format="ext4",
                mount="/",
                name="Foobar",
            ),
            gap=Gap(
                offset=1 << 20,
                size=1000 << 20,
                usable=GapUsable.YES,
            ),
        )
        with mock.patch.object(self.fsc, "create_partition") as create_part:
            with self.assertRaisesRegex(
                StorageInvalidUsageError, r"partition name is not implemented"
            ):
                await self.fsc.v2_add_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        create_part.assert_not_called()

    async def test_v2_add_partition_POST_unsupported_ptable(self):
        self.fsc.locked_probe_data = False
        self.fsc.model, d = make_model_and_disk(ptable="unsupported")
        data = AddPartitionV2(
            disk_id=d.id,
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
            with self.assertRaisesRegex(
                StorageInvalidUsageError, r"unsupported partition table"
            ):
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

    async def test_v2_delete_partition_POST_unsupported_ptable(self):
        self.fsc.locked_probe_data = False
        self.fsc.model, d = make_model_and_disk(ptable="unsupported")
        data = ModifyPartitionV2(
            disk_id=d.id,
            partition=Partition(number=1),
        )
        with mock.patch.object(self.fsc, "delete_partition") as del_part:
            with mock.patch.object(self.fsc, "get_partition"):
                with self.assertRaisesRegex(
                    StorageInvalidUsageError, r"unsupported partition table"
                ):
                    await self.fsc.v2_delete_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        del_part.assert_not_called()

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
        self.fsc.model, d = make_model_and_disk()
        data = ModifyPartitionV2(
            disk_id=d.id,
            partition=Partition(number=1, boot=True),
        )
        existing = make_partition(self.fsc.model, d, size=1000 << 20)
        with mock.patch.object(self.fsc, "partition_disk_handler") as handler:
            with mock.patch.object(self.fsc, "get_partition", return_value=existing):
                with self.assertRaisesRegex(
                    StorageInvalidUsageError, r"changing\ boot"
                ):
                    await self.fsc.v2_edit_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        handler.assert_not_called()

    async def test_v2_edit_partition_POST_change_pname(self):
        self.fsc.locked_probe_data = False
        self.fsc.model, d = make_model_and_disk()
        data = ModifyPartitionV2(
            disk_id=d.id,
            partition=Partition(number=1, name="Foobar"),
        )

        existing = make_partition(
            self.fsc.model, d, size=1000 << 20, partition_name="MyPart"
        )
        with mock.patch.object(self.fsc, "partition_disk_handler") as handler:
            with mock.patch.object(self.fsc, "get_partition", return_value=existing):
                with self.assertRaisesRegex(
                    StorageInvalidUsageError, r"changing partition name"
                ):
                    await self.fsc.v2_edit_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        handler.assert_not_called()

    @parameterized.expand(((None,), ("Foobar",)))
    async def test_v2_edit_partition_POST_preserve_pname(self, name):
        self.fsc.locked_probe_data = False
        self.fsc.model, d = make_model_and_disk()
        data = ModifyPartitionV2(
            disk_id=d.id,
            partition=Partition(number=1, name=name),
        )

        existing = make_partition(
            self.fsc.model, d, size=1000 << 20, partition_name="Foobar"
        )
        with mock.patch.object(self.fsc, "partition_disk_handler") as handler:
            with mock.patch.object(self.fsc, "get_partition", return_value=existing):
                await self.fsc.v2_edit_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        handler.assert_called_once()

    async def test_v2_edit_partition_POST_unsupported_ptable(self):
        self.fsc.locked_probe_data = False
        self.fsc.model, d = make_model_and_disk()
        data = ModifyPartitionV2(
            disk_id=d.id,
            partition=Partition(number=1, boot=True),
        )
        existing = make_partition(self.fsc.model, d, size=1000 << 20)
        d.ptable = "unsupported"
        with mock.patch.object(self.fsc, "partition_disk_handler") as handler:
            with mock.patch.object(self.fsc, "get_partition", return_value=existing):
                with self.assertRaisesRegex(
                    StorageInvalidUsageError, r"unsupported partition table"
                ):
                    await self.fsc.v2_edit_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        handler.assert_not_called()

    async def test_v2_edit_partition_POST(self):
        self.fsc.locked_probe_data = False
        self.fsc.model, d = make_model_and_disk()
        data = ModifyPartitionV2(
            disk_id=d.id,
            partition=Partition(number=1),
        )
        existing = make_partition(self.fsc.model, d, size=1000 << 20)
        with mock.patch.object(self.fsc, "partition_disk_handler") as handler:
            with mock.patch.object(self.fsc, "get_partition", return_value=existing):
                await self.fsc.v2_edit_partition_POST(data)
        self.assertTrue(self.fsc.locked_probe_data)
        handler.assert_called_once()

    async def test_v2_volume_group_DELETE(self):
        self.fsc.locked_probe_data = False
        self.fsc.model, vg = make_model_and_vg()
        with mock.patch.object(self.fsc, "delete_volgroup") as del_volgroup:
            await self.fsc.v2_volume_group_DELETE(id=vg.id)
        self.assertTrue(self.fsc.locked_probe_data)
        del_volgroup.assert_called_once()

    async def test_v2_volume_group_DELETE__inexistent(self):
        self.fsc.locked_probe_data = False
        self.fsc.model = make_model()
        with mock.patch.object(self.fsc, "delete_volgroup") as del_volgroup:
            with self.assertRaisesRegex(
                StorageNotFoundError, r"could not find existing VG"
            ):
                await self.fsc.v2_volume_group_DELETE(id="inexistent")
        self.assertTrue(self.fsc.locked_probe_data)
        del_volgroup.assert_not_called()

    async def test_v2_logical_volume_DELETE(self):
        self.fsc.locked_probe_data = False
        self.fsc.model, lv = make_model_and_lv()
        with mock.patch.object(self.fsc, "delete_logical_volume") as del_lv:
            await self.fsc.v2_logical_volume_DELETE(id=lv.id)
        self.assertTrue(self.fsc.locked_probe_data)
        del_lv.assert_called_once()

    async def test_v2_logical_volume_DELETE__inexistent(self):
        self.fsc.locked_probe_data = False
        self.fsc.model = make_model()
        with mock.patch.object(self.fsc, "delete_logical_volume") as del_lv:
            with self.assertRaisesRegex(
                StorageNotFoundError, r"could not find existing LV"
            ):
                await self.fsc.v2_logical_volume_DELETE(id="inexistent")
        self.assertTrue(self.fsc.locked_probe_data)
        del_lv.assert_not_called()

    async def test_v2_raid_DELETE(self):
        self.fsc.locked_probe_data = False
        self.fsc.model, raid = make_model_and_raid()
        with mock.patch.object(self.fsc, "delete_raid") as del_raid:
            await self.fsc.v2_raid_DELETE(id=raid.id)
        self.assertTrue(self.fsc.locked_probe_data)
        del_raid.assert_called_once()

    async def test_v2_raid_DELETE__inexistent(self):
        self.fsc.locked_probe_data = False
        self.fsc.model = make_model()
        with mock.patch.object(self.fsc, "delete_raid") as del_raid:
            with self.assertRaisesRegex(
                StorageNotFoundError, r"could not find existing RAID"
            ):
                await self.fsc.v2_raid_DELETE(id="inexistent")
        self.assertTrue(self.fsc.locked_probe_data)
        del_raid.assert_not_called()

    async def test_v2_core_boot_recovery_GET(self):
        self.fsc.model = make_model()
        self.fsc.model.guided_configuration = mock.Mock(
            capability=GuidedCapability.CORE_BOOT_ENCRYPTED
        )
        self.fsc.model.set_core_boot_recovery_key("recovery")
        self.assertEqual("recovery", await self.fsc.v2_core_boot_recovery_key_GET())

    async def test_v2_core_boot_recovery_GET__not_yet_configured(self):
        self.fsc.model = make_model()
        self.fsc._configured = False
        with self.assertRaises(
            StorageInvalidUsageError, msg="storage model is not yet configured"
        ):
            await self.fsc.v2_core_boot_recovery_key_GET()

    async def test_v2_core_boot_recovery_GET__not_core_boot(self):
        self.fsc.model = make_model()
        with self.assertRaises(
            StorageInvalidUsageError, msg="not using core boot encrypted"
        ):
            await self.fsc.v2_core_boot_recovery_key_GET()

        self.fsc.model.guided_configuration = mock.Mock(
            capability=GuidedCapability.DIRECT
        )

        with self.assertRaises(
            StorageInvalidUsageError, msg="not using core boot encrypted"
        ):
            await self.fsc.v2_core_boot_recovery_key_GET()

    async def test_v2_core_boot_recovery_GET__not_yet_available(self):
        self.fsc.model = make_model()
        self.fsc.model.guided_configuration = mock.Mock(
            capability=GuidedCapability.CORE_BOOT_ENCRYPTED
        )
        with self.assertRaises(
            StorageInvalidUsageError, msg="recovery key is not yet available"
        ):
            await self.fsc.v2_core_boot_recovery_key_GET()

    @parameterized.expand(
        (
            (
                [
                    snapdtypes.EncryptionFeature.PIN_AUTH,
                    snapdtypes.EncryptionFeature.PASSPHRASE_AUTH,
                ],
                [
                    CoreBootEncryptionFeatures.PIN_AUTH,
                    CoreBootEncryptionFeatures.PASSPHRASE_AUTH,
                ],
            ),
            (
                [snapdtypes.EncryptionFeature.PIN_AUTH],
                [CoreBootEncryptionFeatures.PIN_AUTH],
            ),
            (
                [snapdtypes.EncryptionFeature.PASSPHRASE_AUTH],
                [CoreBootEncryptionFeatures.PASSPHRASE_AUTH],
            ),
        )
    )
    async def test_v2_core_boot_encryption_features_GET(
        self,
        snapd_features: list[snapdtypes.EncryptionFeature],
        expected: list[CoreBootEncryptionFeatures],
    ):
        self.fsc.model = make_model()

        self.fsc._variation_info = {
            "mimimal-enhanced-secureboot": VariationInfo(
                name="minimal-enhanced-secureboot",
                label="enhanced-secureboot-desktop",
                system=snapdtypes.SystemDetails(
                    model=snapdtypes.Model(architecture="amd64", snaps=[]),
                    label="enhanced-secureboot-desktop",
                    storage_encryption=snapdtypes.StorageEncryption(
                        support=snapdtypes.StorageEncryptionSupport.AVAILABLE,
                        storage_safety=snapdtypes.StorageSafety.PREFER_ENCRYPTED,
                        features=snapd_features,
                    ),
                ),
            ),
        }

        self.assertEqual(
            expected, await self.fsc.v2_core_boot_encryption_features_GET()
        )

    async def test_v2_core_boot_encryption_features_GET__snapd_2_67(self):
        self.fsc.model = make_model()

        self.fsc._variation_info = {
            "mimimal-enhanced-secureboot": VariationInfo(
                name="minimal-enhanced-secureboot",
                label="enhanced-secureboot-desktop",
                system=snapdtypes.SystemDetails(
                    model=snapdtypes.Model(architecture="amd64", snaps=[]),
                    label="enhanced-secureboot-desktop",
                    storage_encryption=snapdtypes.StorageEncryption(
                        support=snapdtypes.StorageEncryptionSupport.AVAILABLE,
                        storage_safety=snapdtypes.StorageSafety.PREFER_ENCRYPTED,
                        features=None,
                    ),
                ),
            ),
        }

        self.assertEqual([], await self.fsc.v2_core_boot_encryption_features_GET())

    async def test_v2_core_boot_encryption_features_GET__no_suitable_variation(self):
        self.fsc.model = make_model()

        self.fsc._variation_info = {}

        with self.assertRaises(
            StorageInvalidUsageError, msg="no suitable variation for core boot"
        ):
            await self.fsc.v2_core_boot_encryption_features_GET()

        self.fsc._variation_info = {
            "minimal": VariationInfo(name="minimal", label=None, system=None),
        }

        with self.assertRaises(
            StorageInvalidUsageError, msg="no suitable variation for core boot"
        ):
            await self.fsc.v2_core_boot_encryption_features_GET()

    @parameterized.expand(((True,), (False,)))
    async def test__pre_shutdown_install_started(self, zfsutils_linux_installed: bool):
        self.fsc.reset_partition_only = False
        run = mock.patch.object(self.app.command_runner, "run")
        _all = mock.patch.object(self.fsc.model, "_all")
        which_rv = "/usr/sbin/zpool" if zfsutils_linux_installed else None
        which = mock.patch(
            "subiquity.server.controllers.filesystem.shutil.which",
            return_value=which_rv,
        )
        with run as mock_run, _all, which:
            await self.fsc._pre_shutdown()

        expected_calls = [
            mock.call(["mountpoint", "/target"]),
            mock.call(["umount", "--recursive", "/target"]),
        ]
        if zfsutils_linux_installed:
            expected_calls.append(mock.call(["zpool", "export", "-a"]))
        self.assertEqual(expected_calls, mock_run.mock_calls)

    @parameterized.expand(((True,), (False,)))
    async def test__pre_shutdown_install_not_started(
        self, zfsutils_linux_installed: bool
    ):
        async def fake_run(cmd, **kwargs):
            if cmd == ["mountpoint", "/target"]:
                raise subprocess.CalledProcessError(cmd=cmd, returncode=1)

        self.fsc.reset_partition_only = False
        run = mock.patch.object(self.app.command_runner, "run", side_effect=fake_run)
        which_rv = "/usr/sbin/zpool" if zfsutils_linux_installed else None
        which = mock.patch(
            "subiquity.server.controllers.filesystem.shutil.which",
            return_value=which_rv,
        )
        with run as mock_run, which:
            await self.fsc._pre_shutdown()

        expected_calls = [
            mock.call(["mountpoint", "/target"]),
        ]
        if zfsutils_linux_installed:
            expected_calls.append(mock.call(["zpool", "export", "-a"]))
        self.assertEqual(expected_calls, mock_run.mock_calls)

    async def test_examine_systems(self):
        # In LP: #2037723 and other similar reports, the user selects the
        # source 'ubuntu-desktop-minimal' first and then switches to
        # 'ubuntu-desktop'. The variations of those two sources are different.
        # Upon switching to the new source, we forgot to discard the old
        # variations. This lead to a crash further in the install.
        self.fsc.model = model = make_model(Bootloader.UEFI)
        make_disk(model)
        self.app.base_model.source.current.type = "fsimage"
        self.app.base_model.source.current.variations = {
            "minimal": CatalogEntryVariation(path="", size=1),
        }

        self.app.dr_cfg = DRConfig()
        self.app.dr_cfg.systems_dir_exists = True

        await self.fsc._examine_systems()

        self.assertEqual(len(self.fsc._variation_info), 1)
        self.assertEqual(self.fsc._variation_info["minimal"].name, "minimal")

        self.app.base_model.source.current.variations = {
            "default": CatalogEntryVariation(path="", size=1),
        }

        await self.fsc._examine_systems()

        self.assertEqual(len(self.fsc._variation_info), 1)
        self.assertEqual(self.fsc._variation_info["default"].name, "default")

    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            FilesystemController.autoinstall_schema
        )

        JsonValidator.check_schema(FilesystemController.autoinstall_schema)

    async def test__get_system_api_error_logged(self):
        getter = SystemGetter(self.app)

        @contextlib.asynccontextmanager
        async def mounted(self, *, source_id):
            yield

        mount_mock = mock.patch(
            "subiquity.server.snapd.system_getter.SystemsDirMounter.mounted", mounted
        )

        self.app.snapdapi = snapdapi.make_api_client(
            AsyncSnapd(SnapdConnection(root="/inexistent", sock="snapd"))
        )
        json_body = {
            "type": "error",
            "status-code": 500,
            "status": "Internal Server Error",
            "result": {
                "message": "cannot load assertions for label ...",
            },
        }
        requests_mocker = requests_mock.Mocker()
        requests_mocker.get(
            "http+unix://snapd/v2/systems",
            json={
                "type": "sync",
                "status-code": 200,
                "status": "OK",
                "result": {
                    "systems": [],
                },
            },
            status_code=200,
        )
        requests_mocker.get(
            "http+unix://snapd/v2/systems/enhanced-secureboot-desktop",
            json=json_body,
            status_code=500,
        )

        with mount_mock, requests_mocker:
            with self.assertRaises(requests.exceptions.HTTPError):
                with self.assertLogs(
                    "subiquity.server.snapd.system_getter", level="WARNING"
                ) as logs:
                    await getter.get(
                        variation_name="minimal",
                        label="enhanced-secureboot-desktop",
                        source_id="default",
                    )

            self.assertIn("cannot load assertions for label", logs.output[0])

    def test_start_guided_reformat__no_in_use(self):
        self.fsc.model = model = make_model(Bootloader.UEFI)
        disk = make_disk(model)

        p1 = make_partition(model, disk, size=10 << 30)
        p2 = make_partition(model, disk, size=10 << 30)
        p3 = make_partition(model, disk, size=10 << 30)
        p4 = make_partition(model, disk, size=10 << 30)

        p_del_part = mock.patch.object(
            self.fsc, "delete_partition", wraps=self.fsc.delete_partition
        )
        p_reformat = mock.patch.object(self.fsc, "reformat", wraps=self.fsc.reformat)

        with p_del_part as m_del_part, p_reformat as m_reformat:
            self.fsc.start_guided_reformat(
                GuidedStorageTargetReformat(disk_id=disk.id), disk
            )

        m_reformat.assert_called_once_with(
            disk, ptable=None, wipe="superblock-recursive"
        )
        expected_del_calls = [
            mock.call(
                p1, override_preserve=True, allow_renumbering=False, allow_moving=False
            ),
            mock.call(
                p2, override_preserve=True, allow_renumbering=False, allow_moving=False
            ),
            mock.call(
                p3, override_preserve=True, allow_renumbering=False, allow_moving=False
            ),
            mock.call(
                p4, override_preserve=True, allow_renumbering=False, allow_moving=False
            ),
        ]
        self.assertEqual(expected_del_calls, m_del_part.mock_calls)

    def test_start_guided_reformat__with_in_use(self):
        """In LP: #2083322, start_guided_reformat did not remove all the
        partitions that should have been removed. Because we were iterating
        over device._partitions and calling delete_partition in the body, we
        failed to iterate over some of the partitions."""
        self.fsc.model = model = make_model(Bootloader.UEFI)
        disk = make_disk(model)

        p1 = make_partition(model, disk, size=10 << 30)
        p2 = make_partition(model, disk, size=10 << 30)
        p3 = make_partition(model, disk, size=10 << 30)
        p4 = make_partition(model, disk, size=10 << 30)

        p2._is_in_use = True

        # We use wraps to ensure that the real delete_partition gets called. If
        # we just do a no-op, we won't invalidate the iterator.
        p_del_part = mock.patch.object(
            self.fsc, "delete_partition", wraps=self.fsc.delete_partition
        )
        p_reformat = mock.patch.object(self.fsc, "reformat", wraps=self.fsc.reformat)

        with p_del_part as m_del_part, p_reformat as m_reformat:
            self.fsc.start_guided_reformat(
                GuidedStorageTargetReformat(disk_id=disk.id), disk
            )

        m_reformat.assert_not_called()
        # Not sure why we don't call with "override_preserve=True", like we do
        # in reformat.
        expected_del_calls = [mock.call(p1), mock.call(p3), mock.call(p4)]
        self.assertEqual(expected_del_calls, m_del_part.mock_calls)

    def test_start_guided_erase_install__no_free_space(self):
        self.fsc.model = model = make_model(Bootloader.UEFI, storage_version=2)
        disk = make_disk(model)

        p1 = make_partition(model, disk, size=10 << 30)
        make_partition(model, disk, size=-1, preserve=True)

        gap = self.fsc.start_guided_erase_install(
            GuidedStorageTargetEraseInstall(disk_id=disk.id, partition_number=1), disk
        )

        self.assertEqual(p1.offset, gap.offset)
        self.assertEqual(p1.size, gap.size)

    def test_start_guided_erase_install__free_space_after(self):
        self.fsc.model = model = make_model(Bootloader.UEFI, storage_version=2)
        disk = make_disk(model)

        part = make_partition(model, disk, size=10 << 30)

        _, trailing_gap = gaps.parts_and_gaps(disk)

        gap = self.fsc.start_guided_erase_install(
            GuidedStorageTargetEraseInstall(disk_id=disk.id, partition_number=1), disk
        )

        self.assertEqual(part.offset, gap.offset)
        self.assertEqual(part.size + trailing_gap.size, gap.size)

    def test_start_guided_erase_install__free_space_before(self):
        self.fsc.model = model = make_model(Bootloader.UEFI, storage_version=2)
        disk = make_disk(model)

        part = make_partition(model, disk, size=-1, offset=20 << 30)

        leading_gap, _ = gaps.parts_and_gaps(disk)

        gap = self.fsc.start_guided_erase_install(
            GuidedStorageTargetEraseInstall(disk_id=disk.id, partition_number=1), disk
        )

        self.assertEqual(leading_gap.offset, gap.offset)
        self.assertEqual(part.size + leading_gap.size, gap.size)

    def test_start_guided_erase_install__free_space_before_and_after(self):
        self.fsc.model = model = make_model(Bootloader.UEFI, storage_version=2)
        disk = make_disk(model)

        part = make_partition(model, disk, size=10 << 30, offset=20 << 30)

        leading_gap, _, trailing_gap = gaps.parts_and_gaps(disk)

        gap = self.fsc.start_guided_erase_install(
            GuidedStorageTargetEraseInstall(disk_id=disk.id, partition_number=1), disk
        )

        self.assertEqual(leading_gap.offset, gap.offset)
        self.assertEqual(part.size + leading_gap.size + trailing_gap.size, gap.size)

    async def test_fetch_core_boot_recovery_key(self):
        self.app.snapd = AsyncSnapd(get_fake_connection())
        self.app.snapdapi = snapdapi.make_api_client(self.app.snapd)
        self.fsc._info = mock.Mock(label="my-label")

        with mock.patch.object(
            self.fsc.model, "set_core_boot_recovery_key"
        ) as m_set_key:
            await self.fsc.fetch_core_boot_recovery_key()

        m_set_key.assert_called_once_with("my-recovery-key")

    async def test_finish_install(self):
        self.app.snapdapi = snapdapi.make_api_client(AsyncSnapd(get_fake_connection()))
        variation_info = VariationInfo(
            name="mock",
            label="mock-label",
            system=snapdtypes.SystemDetails(
                label="mock-label",
                volumes={
                    "mockVol": snapdtypes.Volume(schema="mock", structure=None),
                },
                model=snapdtypes.Model(
                    architecture="mock-arch",
                    snaps=[
                        snapdtypes.ModelSnap(
                            name="MockKernel",
                            type=snapdtypes.ModelSnapType.KERNEL,
                            presence=snapdtypes.PresenceValue.REQUIRED,
                            components={
                                "nvidia-510-uda-ko": snapdtypes.PresenceValue.OPTIONAL,
                                "nvidia-510-uda-user": snapdtypes.PresenceValue.OPTIONAL,
                                "foo": snapdtypes.PresenceValue.OPTIONAL,
                                "bar": snapdtypes.PresenceValue.OPTIONAL,
                            },
                            default_channel="foo",
                            id="bar",
                        ),
                        snapdtypes.ModelSnap(
                            name="MockApp1",
                            type=snapdtypes.ModelSnapType.APP,
                            presence=snapdtypes.PresenceValue.REQUIRED,
                            default_channel="foo",
                            id="bar",
                        ),
                        snapdtypes.ModelSnap(
                            name="MockApp2",
                            type=snapdtypes.ModelSnapType.APP,
                            presence=snapdtypes.PresenceValue.OPTIONAL,
                            default_channel="foo",
                            id="bar",
                        ),
                    ],
                ),
                available_optional=snapdtypes.AvailableOptional(
                    snaps=["MockApp2"],
                    components={
                        "MockKernel": [
                            "nvidia-510-uda-ko",
                            "nvidia-510-uda-user",
                            "foo",
                            "bar",
                        ]
                    },
                ),
            ),
        )
        self.fsc._info = variation_info
        with mock.patch.object(snapdapi, "post_and_wait") as mock_post:
            await self.fsc.finish_install(
                context=self.fsc.context,
                kernel_components=["nvidia-510-uda-ko", "nvidia-510-uda-user"],
            )
        mock_post.assert_called_once()

        # Assert installing all optional snaps but only the requested components
        expected_optional_install = snapdtypes.OptionalInstall(
            all=False,
            components={"MockKernel": ["nvidia-510-uda-ko", "nvidia-510-uda-user"]},
            snaps=variation_info.system.available_optional.snaps,
        )
        actual = mock_post.call_args.args[2].optional_install

        self.assertEqual(expected_optional_install, actual)


class TestRunAutoinstallGuided(IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.opts.bootloader = None
        self.app.snapdinfo = mock.Mock(spec=SnapdInfo)
        self.fsc = FilesystemController(self.app)
        self.model = self.fsc.model = make_model()

        # This is needed for examine_systems_task
        self.app.base_model.source.current.type = "fsimage"
        self.app.base_model.source.current.variations = {
            "default": CatalogEntryVariation(path="", size=1),
        }

    async def asyncSetUp(self):
        self.fsc._examine_systems_task.start_sync()

        await self.fsc._examine_systems_task.wait()

    async def test_direct_use_gap__install_media(self):
        """Match directives were previously not honored when using mode: use_gap.
        This made it not possible for the OEM team to install to the
        installation media. LP: #2080608"""
        layout = {
            "name": "direct",
            "mode": "use_gap",
            "match": {
                "install-media": True,
            },
        }

        # The matcher for "install-media": True looks for
        # _has_in_use_partition.
        iso = make_disk(self.model)
        iso._has_in_use_partition = True

        make_disk(self.model)

        p_guided = mock.patch.object(self.fsc, "guided")
        p_guided_choice_v2 = mock.patch(
            "subiquity.server.controllers.filesystem.GuidedChoiceV2",
            wraps=GuidedChoiceV2,
        )
        p_largest_gap = mock.patch(
            "subiquity.server.controllers.filesystem.gaps.largest_gap",
            wraps=gaps.largest_gap,
        )

        with (
            p_guided as m_guided,
            p_guided_choice_v2 as m_guided_choice_v2,
            p_largest_gap as m_largest_gap,
        ):
            await self.fsc.run_autoinstall_guided(layout)

        # largest_gap will call itself recursively, so we should not expect a
        # single call to it.
        m_largest_gap.mock_calls[0] = mock.call([iso])

        m_guided.assert_called_once()
        m_guided_choice_v2.assert_called_once_with(
            target=GuidedStorageTargetUseGap(
                disk_id=iso.id, gap=gaps.largest_gap([iso]), allowed=[]
            ),
            capability=GuidedCapability.DIRECT,
            password=mock.ANY,
            recovery_key=mock.ANY,
            sizing_policy=mock.ANY,
            reset_partition=mock.ANY,
            reset_partition_size=mock.ANY,
        )


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
        self.app.snapdinfo = mock.Mock(spec=SnapdInfo)
        self.controller = FilesystemController(self.app)
        self.controller.supports_resilient_boot = True
        self.controller._examine_systems_task.start_sync()
        self.controller.cryptoswap_options = ["a", "b"]
        self.app.dr_cfg = DRConfig()
        self.app.base_model.source.current.type = "fsimage"
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

    async def test_fixed_reset_partition(self):
        await self._guided_setup(Bootloader.UEFI, "gpt")
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, allowed=default_capabilities
        )
        fixed_reset_size = 12 << 30
        await self.controller.guided(
            GuidedChoiceV2(
                target=target,
                capability=GuidedCapability.DIRECT,
                reset_partition=True,
                reset_partition_size=fixed_reset_size,
            )
        )
        [d1p1, d1p2, d1p3] = self.d1.partitions()
        self.assertEqual("/boot/efi", d1p1.mount)
        self.assertIsNone(d1p2.mount)
        self.assertEqual(fixed_reset_size, d1p2.size)
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

    @parameterized.expand(
        (
            ({}, False, None),
            ({"reset-partition": True}, True, None),
            ({"reset-partition": False}, False, None),
            ({"reset-partition": "12345"}, True, 12345),
            ({"reset-partition": "10G"}, True, 10737418240),
            ({"reset-partition": 100000}, True, 100000),
        )
    )
    async def test_rest_partition_size(
        self, ai_data, reset_partition, reset_partition_size
    ):
        await self._guided_setup(Bootloader.UEFI, "gpt")
        self.controller.guided = mock.AsyncMock()
        layout = ai_data | {"name": "direct"}
        await self.controller.run_autoinstall_guided(layout)
        guided_choice = self.controller.guided.call_args.args[0]
        self.assertEqual(guided_choice.reset_partition, reset_partition)
        self.assertEqual(guided_choice.reset_partition_size, reset_partition_size)

    async def test_guided_direct_BIOS_MSDOS(self):
        await self._guided_setup(Bootloader.BIOS, "msdos")
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, ptable="msdos", allowed=default_capabilities
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
            disk_id=self.d1.id, ptable="msdos", allowed=default_capabilities
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
        [firmware, boot, swap, root] = self.d1.partitions()
        self.assertEqual(p1mnt, firmware.mount)
        self.assertIsNone(boot.mount)
        self.assertIsNone(root.mount)
        self.assertFalse(firmware.preserve)
        self.assertFalse(boot.preserve)
        self.assertFalse(swap.preserve)
        self.assertFalse(root.preserve)
        self.assertEqual("swap", swap.fs().fstype)
        [rpool] = self.model._all(type="zpool", pool="rpool")
        self.assertIsNone(rpool.path)
        self.assertEqual([root], rpool.vdevs)
        self.assertIsNone(rpool.encryption_style)
        self.assertIsNone(rpool.keyfile)
        [bpool] = self.model._all(type="zpool", pool="bpool")
        self.assertIsNone(bpool.path)
        self.assertEqual([boot], bpool.vdevs)
        zfs_rootfs = self.model._mount_for_path("/")
        self.assertEqual("zfs", zfs_rootfs.type)
        zfs_boot = self.model._mount_for_path("/boot")
        self.assertEqual("zfs", zfs_boot.type)

        # checking that these were created
        [userdata] = self.model._all(type="zfs", volume="USERDATA")
        [userdata_home] = self.model._all(type="zfs", path="/home")
        [userdata_root] = self.model._all(type="zfs", path="/root")

    @parameterized.expand(boot_expectations)
    async def test_guided_zfs_luks_keystore(self, bootloader, ptable, p1mnt):
        await self._guided_setup(bootloader, ptable)
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, allowed=default_capabilities
        )
        await self.controller.guided(
            GuidedChoiceV2(
                target=target,
                capability=GuidedCapability.ZFS_LUKS_KEYSTORE,
                password="passw0rd",
            )
        )
        [firmware, boot, swap, root] = self.d1.partitions()
        self.assertEqual(p1mnt, firmware.mount)
        self.assertIsNone(boot.mount)
        self.assertIsNone(root.mount)
        self.assertFalse(firmware.preserve)
        self.assertFalse(boot.preserve)
        self.assertFalse(swap.preserve)
        self.assertFalse(root.preserve)
        self.assertIsNone(swap.fs())
        [dmc] = self.model.all_dm_crypts()
        self.assertEqual("/dev/urandom", dmc.keyfile)
        self.assertEqual(["a", "b"], dmc.options)
        self.assertEqual("swap", dmc.fs().fstype)
        [rpool] = self.model._all(type="zpool", pool="rpool")
        self.assertIsNone(rpool.path)
        self.assertEqual([root], rpool.vdevs)
        self.assertEqual("luks_keystore", rpool.encryption_style)
        with open(rpool.keyfile) as fp:
            self.assertEqual("passw0rd", fp.read())
            # a tempfile is created outside of normal test tempfiles,
            # clean that up
            Path(rpool.keyfile).unlink()
        [bpool] = self.model._all(type="zpool", pool="bpool")
        self.assertIsNone(bpool.path)
        self.assertEqual([boot], bpool.vdevs)
        zfs_rootfs = self.model._mount_for_path("/")
        self.assertEqual("zfs", zfs_rootfs.type)
        zfs_boot = self.model._mount_for_path("/boot")
        self.assertEqual("zfs", zfs_boot.type)

    async def test_guided_zfs_BIOS_MSDOS(self):
        await self._guided_setup(Bootloader.BIOS, "msdos")
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, ptable="msdos", allowed=default_capabilities
        )
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.ZFS)
        )
        [boot, swap, root] = self.d1.partitions()
        self.assertIsNone(boot.mount)
        self.assertIsNone(root.mount)
        self.assertFalse(boot.preserve)
        self.assertFalse(swap.preserve)
        self.assertFalse(root.preserve)
        self.assertEqual("swap", swap.fs().fstype)
        [rpool] = self.model._all(type="zpool", pool="rpool")
        self.assertIsNone(rpool.path)
        self.assertEqual([root], rpool.vdevs)
        [bpool] = self.model._all(type="zpool", pool="bpool")
        self.assertIsNone(bpool.path)
        self.assertEqual([boot], bpool.vdevs)
        zfs_rootfs = self.model._mount_for_path("/")
        self.assertEqual("zfs", zfs_rootfs.type)
        zfs_boot = self.model._mount_for_path("/boot")
        self.assertEqual("zfs", zfs_boot.type)

    @mock.patch("subiquity.server.controllers.filesystem.swap.suggested_swapsize")
    async def test_guided_zfs_swap_size_lp_2034939(self, suggested):
        suggested.return_value = (1 << 30) + 1
        # crash due to add_partition for swap with unaligned size
        await self._guided_setup(Bootloader.UEFI, "gpt")
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, allowed=default_capabilities
        )
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.ZFS)
        )
        # just checking that this doesn't throw

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

    @parameterized.expand([(True, None), (True, "gpt"), (True, "msdos"), (False, None)])
    async def test_autoinstall__reformat_with_ptable(self, include_ptable, ptable):
        self.fsc.model = make_model()

        make_disk(self.fsc.model, id="dev-sdc"),

        layout = {
            "name": "direct",
            "mode": "reformat_disk",
        }

        if include_ptable:
            layout["ptable"] = ptable

        p_guided = mock.patch.object(self.fsc, "guided")
        p_reformat = mock.patch(
            "subiquity.server.controllers.filesystem.GuidedStorageTargetReformat"
        )
        p_has_valid_variation = mock.patch.object(
            self.fsc, "has_valid_non_core_boot_variation", return_value=True
        )

        with p_guided as m_guided, p_reformat as m_reformat, p_has_valid_variation:
            await self.fsc.run_autoinstall_guided(layout)

        expected_ptable = ptable if include_ptable else None
        m_reformat.assert_called_once_with(
            disk_id="dev-sdc", ptable=expected_ptable, allowed=[]
        )
        m_guided.assert_called_once()


class TestGuidedV2(IsolatedAsyncioTestCase):
    async def _setup(self, bootloader, ptable, fix_bios=True, **kw):
        self.app = make_app()
        self.app.opts.bootloader = bootloader.value
        self.app.snapdinfo = mock.Mock(spec=SnapdInfo)
        self.fsc = FilesystemController(app=self.app)
        self.fsc.calculate_suggested_install_min = mock.Mock()
        self.fsc.calculate_suggested_install_min.return_value = 10 << 30
        self.fsc.model = self.model = make_model(bootloader)
        self.fsc._examine_systems_task.start_sync()
        self.app.dr_cfg = DRConfig()
        self.app.base_model.source.current.type = "fsimage"
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
    async def test_small_blank_disk_1GiB(self, bootloader, ptable):
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
    async def test_small_blank_disk_1MiB(self, bootloader, ptable):
        await self._setup(bootloader, ptable, size=1 << 20)
        resp = await self.fsc.v2_guided_GET()

        reformat = GuidedStorageTargetReformat(
            disk_id=self.disk.id,
            allowed=[],
            disallowed=default_capabilities_disallowed_too_small,
        )
        manual = GuidedStorageTargetManual()

        # depending on bootloader/ptable combo, GuidedStorageTargetReformat may
        # show up but it will all be disallowed.
        for target in resp.targets:
            if isinstance(target, GuidedStorageTargetManual):
                self.assertEqual(target, manual)
            elif isinstance(target, GuidedStorageTargetReformat):
                self.assertEqual(target, reformat)
            else:
                raise Exception(f"unexpected target {target}")

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
    async def test_used_half_disk_mounted(self, bootloader, ptable):
        # When a partition is already mounted, it can't be resized.
        await self._setup(bootloader, ptable, size=100 << 30)
        p = make_partition(
            self.model, self.disk, preserve=True, size=50 << 30, is_in_use=True
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

        if ptable != "vtoc" or bootloader == Bootloader.NONE:
            # VTOC has primary_part_limit=3
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
            GuidedStorageTargetManual(),
        ]
        # VTOC does not have enough room for an ESP + 3 partitions, presumably.
        if ptable != "vtoc" or bootloader == Bootloader.NONE:
            expected.insert(
                1,
                GuidedStorageTargetUseGap(
                    disk_id=self.disk.id,
                    allowed=default_capabilities,
                    gap=labels.for_client(gaps.largest_gap(self.disk)),
                ),
            )
        resp = await self.fsc.v2_guided_GET()
        self.assertEqual(expected, resp.targets)
        self.assertEqual(ProbeStatus.DONE, resp.status)

    @parameterized.expand(
        (
            (1, 4, True, True),
            (1, 4, False, True),
            (4, 4, True, False),
            (4, 4, False, False),
            (3, 4, False, True),
            (3, 4, True, False),
            (127, 128, True, False),
            (127, 128, False, True),
        )
    )
    async def test_available_use_gap_scenarios(
        self,
        existing_primaries: int,
        max_primaries: int,
        create_boot_part: bool,
        expected_scenario: bool,
    ):
        await self._setup(Bootloader.NONE, "gpt", fix_bios=True)
        install_min = self.fsc.calculate_suggested_install_min()

        for _ in range(existing_primaries):
            make_partition(self.model, self.disk, preserve=True, size=4 << 20)

        p_max_primaries = mock.patch.object(
            self.fsc.model._partition_alignment_data["gpt"],
            "primary_part_limit",
            max_primaries,
        )
        if create_boot_part:
            boot_plan = boot.CreatePartPlan(mock.Mock(), mock.Mock(), mock.Mock())
        else:
            boot_plan = boot.NoOpBootPlan()
        p_boot_plan = mock.patch(
            "subiquity.server.controllers.filesystem.boot.get_boot_device_plan",
            return_value=boot_plan,
        )
        with p_max_primaries, p_boot_plan:
            scenarios = self.fsc.available_use_gap_scenarios(install_min)

        self.assertEqual(expected_scenario, scenarios != [])

    async def test_available_erase_install_scenarios(self):
        await self._setup(Bootloader.NONE, "gpt", fix_bios=True)
        install_min = self.fsc.calculate_suggested_install_min()

        p1 = make_partition(self.model, self.disk, preserve=True, size=4 << 20)
        p2 = make_partition(self.model, self.disk, preserve=True, size=4 << 20)

        self.model._probe_data["os"] = {
            p1._path(): {
                "label": "Ubuntu",
                "long": "Ubuntu 22.04.1 LTS",
                "type": "linux",
                "version": "22.04.1",
            },
            p2._path(): {
                "label": "Ubuntu",
                "long": "Ubuntu 20.04.7 LTS",
                "type": "linux",
                "version": "20.04.7",
            },
        }

        scenario1, scenario2 = self.fsc.available_erase_install_scenarios(install_min)

        # available_*_scenarios returns a list of tuple having an int as an index
        scenario1 = scenario1[1]
        scenario2 = scenario2[1]

        self.assertIsInstance(scenario1, GuidedStorageTargetEraseInstall)
        self.assertEqual(self.disk.id, scenario1.disk_id)
        self.assertEqual(p1.number, scenario1.partition_number)
        self.assertIsInstance(scenario2, GuidedStorageTargetEraseInstall)
        self.assertEqual(self.disk.id, scenario2.disk_id)
        self.assertEqual(p2.number, scenario2.partition_number)

    async def test_available_erase_install_scenarios__no_os(self):
        await self._setup(Bootloader.NONE, "gpt", fix_bios=True)
        install_min = self.fsc.calculate_suggested_install_min()

        make_partition(self.model, self.disk, preserve=True, size=4 << 20)
        make_partition(self.model, self.disk, preserve=True, size=4 << 20)

        self.assertFalse(self.fsc.available_erase_install_scenarios(install_min))

    async def test_available_erase_install_scenarios__full_primaries(self):
        await self._setup(Bootloader.UEFI, "dos", fix_bios=True)
        install_min = self.fsc.calculate_suggested_install_min()

        p1 = make_partition(self.model, self.disk, preserve=True, size=4 << 20)
        p2 = make_partition(self.model, self.disk, preserve=True, size=4 << 20)
        make_partition(self.model, self.disk, preserve=True, size=4 << 20)
        make_partition(self.model, self.disk, preserve=True, size=4 << 20)

        self.model._probe_data["os"] = {
            p1._path(): {
                "label": "Ubuntu",
                "long": "Ubuntu 22.04.1 LTS",
                "type": "linux",
                "version": "22.04.1",
            },
            p2._path(): {
                "label": "Ubuntu",
                "long": "Ubuntu 20.04.7 LTS",
                "type": "linux",
                "version": "20.04.7",
            },
        }

        self.assertFalse(self.fsc.available_erase_install_scenarios(install_min))

    async def test_available_erase_install_scenarios__with_logical_partitions(self):
        await self._setup(Bootloader.UEFI, "dos", fix_bios=True)
        install_min = self.fsc.calculate_suggested_install_min()

        model, disk = self.model, self.disk
        # Sizes are irrelevant
        size = 4 << 20

        # This is inspired from threebuntu-on-msdos.json
        p1 = make_partition(model, disk, preserve=True, size=size)
        make_partition(model, disk, preserve=True, size=size * 4, flag="extended")
        make_partition(model, disk, preserve=True, size=size)  # This is the ESP
        p5 = make_partition(model, disk, preserve=True, size=size, flag="logical")
        p6 = make_partition(model, disk, preserve=True, size=size, flag="logical")

        self.model._probe_data["os"] = {
            p1._path(): {
                "label": "Ubuntu",
                "long": "Ubuntu 20.04.4 LTS",
                "type": "linux",
                "version": "20.04.4",
            },
            p5._path(): {
                "label": "Ubuntu1",
                "long": "Ubuntu 21.10",
                "type": "linux",
                "version": "21.10",
            },
            p6._path(): {
                "label": "Ubuntu2",
                "long": "Ubuntu 22.04 LTS",
                "type": "linux",
                "version": "22.04",
            },
        }

        indexed_scenarios = self.fsc.available_erase_install_scenarios(install_min)

        scenarios = [indexed_scenario[1] for indexed_scenario in indexed_scenarios]
        sorted_scenarios = sorted(
            scenarios, key=lambda sc: (sc.disk_id, sc.partition_number)
        )
        self.assertEqual(1, sorted_scenarios[0].partition_number)
        self.assertEqual(5, sorted_scenarios[1].partition_number)
        self.assertEqual(6, sorted_scenarios[2].partition_number)
        self.assertEqual(3, len(sorted_scenarios))

    async def test_resize_has_enough_room_for_partitions__one_primary(self):
        await self._setup(Bootloader.NONE, "gpt", fix_bios=True)

        p = make_partition(self.model, self.disk, preserve=True, size=4 << 20)

        self.assertTrue(self.fsc.resize_has_enough_room_for_partitions(self.disk, p))

    async def test_resize_has_enough_room_for_partitions__full_primaries(self):
        await self._setup(Bootloader.NONE, "dos", fix_bios=True)

        p1 = make_partition(self.model, self.disk, preserve=True, size=4 << 20)
        p2 = make_partition(self.model, self.disk, preserve=True, size=4 << 20)
        p3 = make_partition(self.model, self.disk, preserve=True, size=4 << 20)
        p4 = make_partition(self.model, self.disk, preserve=True, size=4 << 20)

        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(self.disk, p1))
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(self.disk, p2))
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(self.disk, p3))
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(self.disk, p4))

    @mock.patch("subiquity.server.controllers.filesystem.boot.get_boot_device_plan")
    async def test_resize_has_enough_room_for_partitions__one_more(self, p_boot_plan):
        await self._setup(Bootloader.NONE, "dos", fix_bios=True)

        model = self.model
        disk = self.disk
        # Sizes are irrelevant
        size = 4 << 20
        p1 = make_partition(model, disk, preserve=True, size=size)
        p2 = make_partition(model, disk, preserve=True, size=size)
        p3 = make_partition(model, disk, preserve=True, size=size)

        p_boot_plan.return_value = boot.CreatePartPlan(
            mock.Mock(), mock.Mock(), mock.Mock()
        )
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(disk, p1))
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(disk, p2))
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(disk, p3))

        p_boot_plan.return_value = boot.NoOpBootPlan()
        self.assertTrue(self.fsc.resize_has_enough_room_for_partitions(disk, p1))
        self.assertTrue(self.fsc.resize_has_enough_room_for_partitions(disk, p2))
        self.assertTrue(self.fsc.resize_has_enough_room_for_partitions(disk, p3))

    @mock.patch("subiquity.server.controllers.filesystem.boot.get_boot_device_plan")
    async def test_resize_has_enough_room_for_partitions__logical(self, p_boot_plan):
        await self._setup(Bootloader.NONE, "dos", fix_bios=True)

        model = self.model
        disk = self.disk
        # Sizes are irrelevant
        size = 4 << 20
        p1 = make_partition(model, disk, preserve=True, size=size)
        p2 = make_partition(model, disk, preserve=True, size=size * 2, flag="extended")
        p5 = make_partition(model, disk, preserve=True, size=size, flag="logical")
        p6 = make_partition(model, disk, preserve=True, size=size, flag="logical")
        p3 = make_partition(model, disk, preserve=True, size=size)
        p4 = make_partition(model, disk, preserve=True, size=size)

        p_boot_plan.return_value = boot.CreatePartPlan(
            mock.Mock(), mock.Mock(), mock.Mock()
        )
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(disk, p1))
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(disk, p2))
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(disk, p3))
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(disk, p4))
        # we're installing in a logical partition, but we still have not enough
        # room to apply the boot plan.
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(disk, p5))
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(disk, p6))

        p_boot_plan.return_value = boot.NoOpBootPlan()
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(disk, p1))
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(disk, p2))
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(disk, p3))
        self.assertFalse(self.fsc.resize_has_enough_room_for_partitions(disk, p4))
        # if we're installing in a logical partition, we have enough room
        self.assertTrue(self.fsc.resize_has_enough_room_for_partitions(disk, p5))
        self.assertTrue(self.fsc.resize_has_enough_room_for_partitions(disk, p6))


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
        self.fsc._probe_firmware_task.task = mock.Mock()
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
        ctrler = make_nvme_controller(
            model=self.model, transport="tcp", tcp_addr="172.16.82.78", tcp_port=4420
        )

        d1 = make_disk(self.model)
        d2 = make_disk(self.model)
        make_disk(self.model, nvme_controller=ctrler)
        make_partition(self.model, d1, size=gaps.largest_gap_size(d1), preserve=True)
        if bootloader == Bootloader.NONE:
            # NONE will always pass the boot check, even on a full disk
            # .. well unless if it is a "remote" disk.
            bootable = set([d1.id, d2.id])
        else:
            bootable = set([d2.id])
        resp = await self.fsc.v2_GET()
        for d in resp.disks:
            self.assertEqual(d.id in bootable, d.can_be_boot_device)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_get_boot_disks_no_remote(self, bootloader, ptable):
        self._setup(bootloader, ptable)
        d = make_disk(self.model)
        with mock.patch.object(d, "on_remote_storage", return_value=False):
            resp = await self.fsc.v2_GET()
        self.assertTrue(resp.disks[0].can_be_boot_device)
        with mock.patch.object(d, "on_remote_storage", return_value=True):
            resp = await self.fsc.v2_GET()
        self.assertFalse(resp.disks[0].can_be_boot_device)


class TestCoreBootInstallMethods(IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.command_runner = mock.AsyncMock()
        self.app.opts.bootloader = "UEFI"
        self.app.opts.block_probing_timeout = None
        self.app.prober = mock.Mock()
        self.app.prober.get_storage = mock.AsyncMock()
        self.app.prober.get_firmware = mock.AsyncMock(
            return_value={
                "bios-vendor": None,
                "bios-version": None,
                "bios-release-date": None,
            }
        )
        self.app.snapdapi = snapdapi.make_api_client(AsyncSnapd(get_fake_connection()))
        self.app.snapdinfo = mock.Mock(spec=SnapdInfo)
        self.app.dr_cfg = DRConfig()
        self.app.dr_cfg.systems_dir_exists = True
        self.app.controllers.Source.get_handler.return_value = TrivialSourceHandler("")
        self.app.base_model.source.search_drivers = False
        self.fsc = FilesystemController(app=self.app)
        self.fsc._configured = True
        self.fsc.model = make_model(Bootloader.UEFI)
        self.choice = GuidedChoiceV2(
            target=GuidedStorageTargetReformat,
            capability=GuidedCapability.CORE_BOOT_ENCRYPTED,
        )

        @contextlib.asynccontextmanager
        async def mounted(self, *, source_id):
            yield

        p = mock.patch(
            "subiquity.server.snapd.system_getter.SystemsDirMounter.mounted", mounted
        )
        p.start()
        self.addCleanup(p.stop)

    def _add_details_for_structures(self, structures):
        self.fsc._info = VariationInfo(
            name="foo",
            label="system",
            system=snapdtypes.SystemDetails(
                label="system",
                volumes={
                    "pc": snapdtypes.Volume(schema="gpt", structure=structures),
                },
                model=snapdtypes.Model(
                    architecture="amd64",
                    snaps=[],
                ),
            ),
        )

    @parameterized.expand(
        (
            [None, None],
            [
                {"password": "asdf"},
                VolumesAuth(
                    mode=VolumesAuthMode.PASSPHRASE, passphrase="asdf", pin=None
                ),
            ],
            [
                {"pin": "1234"},
                VolumesAuth(mode=VolumesAuthMode.PIN, passphrase=None, pin="1234"),
            ],
        )
    )
    async def test_guided_core_boot(self, va_input, va_expected):
        disk = make_disk(self.fsc.model)
        arbitrary_uuid = str(uuid.uuid4())
        self._add_details_for_structures(
            [
                snapdtypes.VolumeStructure(
                    type="83,0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    offset=1 << 20,
                    size=1 << 30,
                    filesystem="ext4",
                    name="one",
                ),
                snapdtypes.VolumeStructure(
                    type=arbitrary_uuid, offset=2 << 30, size=1 << 30, filesystem="ext4"
                ),
            ]
        )
        if va_input is not None:
            self.choice = attrs.evolve(self.choice, **va_input)
        await self.fsc.guided_core_boot(disk, self.choice)
        if va_expected is None:
            self.assertIsNone(self.fsc._volumes_auth)
        else:
            self.assertEqual(va_expected, self.fsc._volumes_auth)
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
                snapdtypes.VolumeStructure(
                    type="0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    offset=1 << 20,
                    size=1 << 30,
                    filesystem="ext4",
                ),
            ]
        )
        await self.fsc.guided_core_boot(disk, self.choice)
        self.assertIsNone(self.fsc._volumes_auth)
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
                snapdtypes.VolumeStructure(
                    type="0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    offset=1 << 20,
                    size=1 << 30,
                    filesystem=None,
                ),
            ]
        )
        await self.fsc.guided_core_boot(disk, self.choice)
        self.assertIsNone(self.fsc._volumes_auth)
        [part] = disk.partitions()
        self.assertEqual(existing_part, part)
        self.assertEqual(existing_part.wipe, None)

    async def test_guided_core_boot_system_data(self):
        disk = make_disk(self.fsc.model)
        self._add_details_for_structures(
            [
                snapdtypes.VolumeStructure(
                    type="21686148-6449-6E6F-744E-656564454649",
                    offset=1 << 20,
                    name="BIOS Boot",
                    size=1 << 20,
                    role="",
                    filesystem="",
                ),
                snapdtypes.VolumeStructure(
                    type="0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    offset=2 << 20,
                    name="ptname",
                    size=2 << 30,
                    role=snapdtypes.Role.SYSTEM_DATA,
                    filesystem="ext4",
                ),
            ]
        )
        await self.fsc.guided_core_boot(disk, self.choice)
        self.assertIsNone(self.fsc._volumes_auth)
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
        self.app.base_model.source.current.type = "fsimage"
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
        with mock.patch.object(self.fsc, "configured") as m_configured:
            await self.fsc.v2_guided_POST(choice)
        m_configured.assert_called_once()

        self.assertEqual(model.storage_version, 2)

        partition_count = len(
            [
                structure
                for structure in self.fsc._info.system.volumes["pc"].structure
                if structure.role != snapdtypes.Role.MBR
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
            mocked.return_value = snapdtypes.SystemActionResponseSetupEncryption(
                encrypted_devices={
                    snapdtypes.Role.SYSTEM_DATA: "enc-system-data",
                },
            )
            await self.fsc.setup_encryption(context=self.fsc.context)

        # setup_encryption mutates the filesystem model objects to
        # reference the newly created encrypted objects so re-read the
        # mount to device mapping.
        mounts = {m.path: m.device.volume for m in model._all(type="mount")}
        self.assertEqual(mounts["/"].path, "enc-system-data")

        with mock.patch.object(
            snapdapi, "post_and_wait", new_callable=mock.AsyncMock
        ) as mocked:
            await self.fsc.finish_install(
                context=self.fsc.context, kernel_components=[]
            )
        mocked.assert_called_once()
        [call] = mocked.mock_calls
        request = call.args[2]
        self.assertEqual(request.action, snapdtypes.SystemAction.INSTALL)
        self.assertEqual(request.step, snapdtypes.SystemActionStep.FINISH)

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
                if structure.role != snapdtypes.Role.MBR
            ]
        )
        self.assertEqual(partition_count, len(disk.partitions()))

    async def test_from_sample_data_defective(self):
        self.fsc.model = model = make_model(Bootloader.UEFI)
        make_disk(model)
        self.app.base_model.source.current.type = "fsimage"
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


class TestMatchingDisks(IsolatedAsyncioTestCase):
    def setUp(self):
        bootloader = Bootloader.UEFI
        self.app = make_app()
        self.app.opts.bootloader = bootloader.value
        self.fsc = FilesystemController(app=self.app)
        self.fsc.model = make_model(bootloader)

    def test_no_match_raises_AutoinstallError(self):
        with self.assertRaises(AutoinstallError):
            self.fsc.get_bootable_matching_disk({"size": "largest"})
        with self.assertRaises(AutoinstallError):
            self.fsc.get_bootable_matching_disks({"size": "largest"})

    def test_two_matches(self):
        d1 = make_disk(self.fsc.model, size=10 << 30)
        d2 = make_disk(self.fsc.model, size=20 << 30)
        self.assertEqual(d2, self.fsc.get_bootable_matching_disk({"size": "largest"}))
        self.assertEqual(d1, self.fsc.get_bootable_matching_disk({"size": "smallest"}))
        self.assertEqual(
            [d2, d1], self.fsc.get_bootable_matching_disks({"size": "largest"})
        )
        self.assertEqual(
            [d1, d2], self.fsc.get_bootable_matching_disks({"size": "smallest"})
        )

    @mock.patch("subiquity.common.filesystem.boot.can_be_boot_device")
    def test_actually_match_raid(self, m_cbb):
        r1 = make_raid(self.fsc.model)
        m_cbb.return_value = True
        # a size based check will make the raid not largest because of 65MiB of
        # overhead
        actual = self.fsc.get_bootable_matching_disk({"path": "/dev/md/*"})
        self.assertEqual(r1, actual)


class TestResetPartitionLookAhead(IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.opts.bootloader = None
        self.fsc = FilesystemController(app=self.app)

    @parameterized.expand(
        # (config, is reset only)
        (
            ({}, False),
            (
                {
                    "storage": {},
                },
                False,
            ),
            (
                {
                    "storage": {
                        "layout": {
                            "name": "direct",
                            "reset-partition": True,
                        },
                    },
                },
                False,
            ),
            (
                {
                    "storage": {
                        "layout": {
                            "reset-partition-only": True,
                        },
                    },
                },
                True,
            ),
        )
    )
    def test_is_reset_partition_only_utility(self, config, expected):
        """Test is_reset_partition_only utility"""

        self.app.autoinstall_config = config

        self.assertEqual(self.fsc.is_reset_partition_only(), expected)


class TestGuidedChoiceValidation(IsolatedAsyncioTestCase):
    def test_pin_and_pass(self):
        reformat = GuidedStorageTargetReformat
        tpmfde = GuidedCapability.CORE_BOOT_ENCRYPTED
        choice = GuidedChoiceV2(
            target=reformat, capability=tpmfde, pin="01234", password="asdf"
        )
        with self.assertRaises(StorageInvalidUsageError):
            choice.validate()

    @parameterized.expand(
        (
            (GuidedCapability.MANUAL, False, False),
            (GuidedCapability.LVM_LUKS, False, True),
            (GuidedCapability.CORE_BOOT_ENCRYPTED, True, True),
            (GuidedCapability.CORE_BOOT_PREFER_ENCRYPTED, True, True),
        )
    )
    def test_capability_pin_pass_validation(self, capability, pin_ok, pass_ok):
        def maybe_assert_raises(ok: bool):
            if ok:
                return contextlib.nullcontext()
            else:
                return self.assertRaises(StorageInvalidUsageError)

        reformat = GuidedStorageTargetReformat
        choice = GuidedChoiceV2(target=reformat, capability=capability)
        pin_choice = attrs.evolve(choice, pin="01234")
        with maybe_assert_raises(pin_ok):
            pin_choice.validate()

        passphrase_choice = attrs.evolve(choice, password="asdf")
        with maybe_assert_raises(pass_ok):
            passphrase_choice.validate()


class TestCalculateEntropy(IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.opts.bootloader = None
        self.fsc = FilesystemController(app=self.app)
        self.fsc._info = mock.Mock()
        self.fsc._info.needs_systems_mount = False

    async def test_both_pin_and_pass(self):
        with self.assertRaises(StorageInvalidUsageError):
            await self.fsc.v2_calculate_entropy_POST(
                CalculateEntropyRequest(passphrase="asdf", pin="01234")
            )

    async def test_neither_pin_and_pass(self):
        with self.assertRaises(StorageInvalidUsageError):
            await self.fsc.v2_calculate_entropy_POST(CalculateEntropyRequest())

    @parameterized.expand(
        (
            ["asdf"],
            ["+1"],
            ["-1"],
        )
    )
    async def test_invalid_pin(self, pin):
        with self.assertRaises(StorageInvalidUsageError):
            await self.fsc.v2_calculate_entropy_POST(CalculateEntropyRequest(pin=pin))

    @parameterized.expand(
        (
            (
                "pin",
                "012",
                EntropyResponse(False, 3, 4, 5, failure_reasons=["low-entropy"]),
                "invalid-pin",
            ),
            (
                "passphrase",
                "asdf",
                EntropyResponse(False, 8, 8, 10, failure_reasons=["low-entropy"]),
                "invalid-passphrase",
            ),
        )
    )
    async def test_stub_invalid(self, type_, pin_or_pass, expected_entropy, kind):
        label = self.fsc._info.label
        self.app.snapd = AsyncSnapd(get_fake_connection())

        with mock.patch(
            "subiquity.server.controllers.filesystem.snapdapi.make_api_client",
            return_value=self.app.snapdapi,
        ):
            with mock.patch.object(
                self.app.snapdapi.v2.systems[label],
                "POST",
                new_callable=mock.AsyncMock,
                return_value=snapdtypes.EntropyCheckResponse(
                    kind=kind,
                    message="did not pass quality checks",
                    value=snapdtypes.InsufficientEntropyDetails(
                        reasons=[snapdtypes.InsufficientEntropyReasons.LOW_ENTROPY],
                        entropy_bits=expected_entropy.entropy_bits,
                        min_entropy_bits=expected_entropy.min_entropy_bits,
                        optimal_entropy_bits=expected_entropy.optimal_entropy_bits,
                    ),
                ),
            ):
                actual = await self.fsc.v2_calculate_entropy_POST(
                    CalculateEntropyRequest(**{type_: pin_or_pass})
                )

        self.assertEqual(expected_entropy, actual)

    @parameterized.expand(
        (
            ("pin", "01234", EntropyResponse(True, 5, 4, 8)),
            ("passphrase", "asdfasdf", EntropyResponse(True, 8, 8, 16)),
        )
    )
    async def test_stub_valid(self, type_, pin_or_pass, expected_entropy):
        label = self.fsc._info.label
        self.app.snapd = AsyncSnapd(get_fake_connection())

        with mock.patch(
            "subiquity.server.controllers.filesystem.snapdapi.make_api_client",
            return_value=self.app.snapdapi,
        ):
            with mock.patch.object(
                self.app.snapdapi.v2.systems[label],
                "POST",
                new_callable=mock.AsyncMock,
                return_value=snapdtypes.EntropyCheckResponse(
                    entropy_bits=expected_entropy.entropy_bits,
                    min_entropy_bits=expected_entropy.min_entropy_bits,
                    optimal_entropy_bits=expected_entropy.optimal_entropy_bits,
                ),
            ):
                actual = await self.fsc.v2_calculate_entropy_POST(
                    CalculateEntropyRequest(**{type_: pin_or_pass})
                )

        self.assertEqual(expected_entropy, actual)
