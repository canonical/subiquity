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
from unittest import mock, IsolatedAsyncioTestCase
import uuid

from curtin.commands.extract import TrivialSourceHandler

from subiquitycore.tests.parameterized import parameterized

from subiquitycore.snapd import AsyncSnapd, get_fake_connection
from subiquitycore.tests.mocks import make_app
from subiquitycore.utils import matching_dicts
from subiquitycore.tests.util import random_string

from subiquity.common.filesystem import gaps
from subiquity.common.types import (
    Bootloader,
    GuidedCapability,
    GuidedChoiceV2,
    GuidedStorageTargetReformat,
    GuidedStorageTargetResize,
    GuidedStorageTargetUseGap,
    ProbeStatus,
    SizingPolicy,
    )
from subiquity.models.filesystem import dehumanize_size
from subiquity.models.tests.test_filesystem import (
    make_disk,
    make_model,
    make_partition,
    )
from subiquity.server import snapdapi
from subiquity.server.controllers.filesystem import FilesystemController
from subiquity.server.dryrun import DRConfig

bootloaders = [(bl, ) for bl in list(Bootloader)]
bootloaders_and_ptables = [(bl, pt)
                           for bl in list(Bootloader)
                           for pt in ('gpt', 'msdos', 'vtoc')]


default_capabilities = [
    GuidedCapability.DIRECT,
    GuidedCapability.LVM,
    GuidedCapability.LVM_LUKS,
    ]


class TestSubiquityControllerFilesystem(IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.opts.bootloader = 'UEFI'
        self.app.report_start_event = mock.Mock()
        self.app.report_finish_event = mock.Mock()
        self.app.prober = mock.Mock()
        self.fsc = FilesystemController(app=self.app)
        self.fsc._configured = True

    async def test_probe_restricted(self):
        await self.fsc._probe_once(context=None, restricted=True)
        self.app.prober.get_storage.assert_called_with({'blockdev'})

    async def test_probe_os_prober_false(self):
        self.app.opts.use_os_prober = False
        await self.fsc._probe_once(context=None, restricted=False)
        actual = self.app.prober.get_storage.call_args.args[0]
        self.assertTrue({'defaults'} <= actual)
        self.assertNotIn('os', actual)

    async def test_probe_os_prober_true(self):
        self.app.opts.use_os_prober = True
        await self.fsc._probe_once(context=None, restricted=False)
        actual = self.app.prober.get_storage.call_args.args[0]
        self.assertTrue({'defaults', 'os'} <= actual)


class TestGuided(IsolatedAsyncioTestCase):
    boot_expectations = [
        (Bootloader.UEFI, 'gpt', '/boot/efi'),
        (Bootloader.UEFI, 'msdos', '/boot/efi'),
        (Bootloader.BIOS, 'gpt', None),
        # BIOS + msdos is different
        (Bootloader.PREP, 'gpt', None),
        (Bootloader.PREP, 'msdos', None),
    ]

    def _guided_setup(self, bootloader, ptable, storage_version=None):
        self.app = make_app()
        self.app.opts.bootloader = bootloader.value
        self.controller = FilesystemController(self.app)
        self.controller.supports_resilient_boot = True
        self.model = make_model(bootloader, storage_version)
        self.controller.model = self.model
        self.model._probe_data = {'blockdev': {}}
        self.d1 = make_disk(self.model, ptable=ptable)

    @parameterized.expand(boot_expectations)
    async def test_guided_direct(self, bootloader, ptable, p1mnt):
        self._guided_setup(bootloader, ptable)
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, capabilities=default_capabilities)
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.DIRECT))
        [d1p1, d1p2] = self.d1.partitions()
        self.assertEqual(p1mnt, d1p1.mount)
        self.assertEqual('/', d1p2.mount)
        self.assertFalse(d1p1.preserve)
        self.assertFalse(d1p2.preserve)
        self.assertIsNone(gaps.largest_gap(self.d1))

    async def test_guided_direct_BIOS_MSDOS(self):
        self._guided_setup(Bootloader.BIOS, 'msdos')
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, capabilities=default_capabilities)
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.DIRECT))
        [d1p1] = self.d1.partitions()
        self.assertEqual('/', d1p1.mount)
        self.assertFalse(d1p1.preserve)
        self.assertIsNone(gaps.largest_gap(self.d1))

    @parameterized.expand(boot_expectations)
    async def test_guided_lvm(self, bootloader, ptable, p1mnt):
        self._guided_setup(bootloader, ptable)
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, capabilities=default_capabilities)
        await self.controller.guided(GuidedChoiceV2(
            target=target, capability=GuidedCapability.LVM))
        [d1p1, d1p2, d1p3] = self.d1.partitions()
        self.assertEqual(p1mnt, d1p1.mount)
        self.assertEqual('/boot', d1p2.mount)
        self.assertEqual(None, d1p3.mount)
        self.assertFalse(d1p1.preserve)
        self.assertFalse(d1p2.preserve)
        self.assertFalse(d1p3.preserve)
        [vg] = self.model._all(type='lvm_volgroup')
        [part] = list(vg.devices)
        self.assertEqual(d1p3, part)
        self.assertIsNone(gaps.largest_gap(self.d1))

    async def test_guided_lvm_BIOS_MSDOS(self):
        self._guided_setup(Bootloader.BIOS, 'msdos')
        target = GuidedStorageTargetReformat(
            disk_id=self.d1.id, capabilities=default_capabilities)
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.LVM))
        [d1p1, d1p2] = self.d1.partitions()
        self.assertEqual('/boot', d1p1.mount)
        [vg] = self.model._all(type='lvm_volgroup')
        [part] = list(vg.devices)
        self.assertEqual(d1p2, part)
        self.assertEqual(None, d1p2.mount)
        self.assertFalse(d1p1.preserve)
        self.assertFalse(d1p2.preserve)
        self.assertIsNone(gaps.largest_gap(self.d1))

    def _guided_side_by_side(self, bl, ptable):
        self._guided_setup(bl, ptable, storage_version=2)
        self.controller.add_boot_disk(self.d1)
        for p in self.d1._partitions:
            p.preserve = True
            if bl == Bootloader.UEFI:
                # let it pass the is_esp check
                self.model._probe_data['blockdev'][p._path()] = {
                    "ID_PART_ENTRY_TYPE": str(0xef)
                }
        # Make it more interesting with other partitions.
        # Also create the extended part if needed.
        g = gaps.largest_gap(self.d1)
        make_partition(self.model, self.d1, preserve=True,
                       size=10 << 30, offset=g.offset)
        if ptable == 'msdos':
            g = gaps.largest_gap(self.d1)
            make_partition(self.model, self.d1, preserve=True,
                           flag='extended', size=g.size, offset=g.offset)
            g = gaps.largest_gap(self.d1)
            make_partition(self.model, self.d1, preserve=True,
                           flag='logical', size=10 << 30, offset=g.offset)

    @parameterized.expand(
        [(bl, pt, flag)
         for bl in list(Bootloader)
         for pt, flag in (
             ('msdos', 'logical'),
             ('gpt', None)
         )]
    )
    async def test_guided_direct_side_by_side(self, bl, pt, flag):
        self._guided_side_by_side(bl, pt)
        parts_before = self.d1._partitions.copy()
        gap = gaps.largest_gap(self.d1)
        target = GuidedStorageTargetUseGap(
            disk_id=self.d1.id, gap=gap, capabilities=default_capabilities)
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.DIRECT))
        parts_after = gaps.parts_and_gaps(self.d1)[:-1]
        self.assertEqual(parts_before, parts_after)
        p = gaps.parts_and_gaps(self.d1)[-1]
        self.assertEqual('/', p.mount)
        self.assertEqual(flag, p.flag)

    @parameterized.expand(
        [(bl, pt, flag)
         for bl in list(Bootloader)
         for pt, flag in (
             ('msdos', 'logical'),
             ('gpt', None)
         )]
    )
    async def test_guided_lvm_side_by_side(self, bl, pt, flag):
        self._guided_side_by_side(bl, pt)
        parts_before = self.d1._partitions.copy()
        gap = gaps.largest_gap(self.d1)
        target = GuidedStorageTargetUseGap(
            disk_id=self.d1.id, gap=gap, capabilities=default_capabilities)
        await self.controller.guided(
            GuidedChoiceV2(target=target, capability=GuidedCapability.LVM))
        parts_after = gaps.parts_and_gaps(self.d1)[:-2]
        self.assertEqual(parts_before, parts_after)
        p_boot, p_data = gaps.parts_and_gaps(self.d1)[-2:]
        self.assertEqual('/boot', p_boot.mount)
        self.assertEqual(flag, p_boot.flag)
        self.assertEqual(None, p_data.mount)
        self.assertEqual(flag, p_data.flag)


class TestLayout(IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.opts.bootloader = None
        self.fsc = FilesystemController(app=self.app)

    @parameterized.expand([('reformat_disk',), ('use_gap',)])
    async def test_good_modes(self, mode):
        self.fsc.validate_layout_mode(mode)

    @parameterized.expand([('resize_biggest',), ('use_free',)])
    async def test_bad_modes(self, mode):
        with self.assertRaises(ValueError):
            self.fsc.validate_layout_mode(mode)


class TestGuidedV2(IsolatedAsyncioTestCase):
    def _setup(self, bootloader, ptable, fix_bios=True, **kw):
        self.app = make_app()
        self.app.opts.bootloader = bootloader.value
        self.fsc = FilesystemController(app=self.app)
        self.fsc.calculate_suggested_install_min = mock.Mock()
        self.fsc.calculate_suggested_install_min.return_value = 10 << 30
        self.fsc.model = self.model = make_model(bootloader)
        self.disk = make_disk(self.model, ptable=ptable, **kw)
        self.model.storage_version = 2
        self.fs_probe = {}
        self.fsc.model._probe_data = {
            'blockdev': {},
            'filesystem': self.fs_probe,
            }
        self.fsc._probe_task.task = mock.Mock()
        self.fsc._get_system_task.task = mock.Mock()
        if bootloader == Bootloader.BIOS and ptable != 'msdos' and fix_bios:
            make_partition(self.model, self.disk, preserve=True,
                           flag='bios_grub', size=1 << 20, offset=1 << 20)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_blank_disk(self, bootloader, ptable):
        # blank disks should not report a UseGap case
        self._setup(bootloader, ptable, fix_bios=False)
        expected = [
            GuidedStorageTargetReformat(
                disk_id=self.disk.id, capabilities=default_capabilities),
            ]
        resp = await self.fsc.v2_guided_GET()
        self.assertEqual(expected, resp.possible)
        self.assertEqual(ProbeStatus.DONE, resp.status)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_probing(self, bootloader, ptable):
        self._setup(bootloader, ptable, fix_bios=False)
        self.fsc._probe_task.task = None
        resp = await self.fsc.v2_guided_GET()
        self.assertEqual([], resp.possible)
        self.assertEqual(ProbeStatus.PROBING, resp.status)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_small_blank_disk(self, bootloader, ptable):
        self._setup(bootloader, ptable, size=1 << 30)
        resp = await self.fsc.v2_guided_GET()
        self.assertEqual(0, len(resp.possible))

    @parameterized.expand(bootloaders_and_ptables)
    async def test_used_half_disk(self, bootloader, ptable):
        self._setup(bootloader, ptable, size=100 << 30)
        p = make_partition(self.model, self.disk, preserve=True, size=50 << 30)
        gap_offset = p.size + p.offset
        self.fs_probe[p._path()] = {'ESTIMATED_MIN_SIZE': 1 << 20}
        resp = await self.fsc.v2_guided_GET()

        reformat = resp.possible.pop(0)
        self.assertEqual(
            GuidedStorageTargetReformat(
                disk_id=self.disk.id, capabilities=default_capabilities),
            reformat)

        use_gap = resp.possible.pop(0)
        self.assertEqual(self.disk.id, use_gap.disk_id)
        self.assertEqual(gap_offset, use_gap.gap.offset)

        resize = resp.possible.pop(0)
        self.assertEqual(self.disk.id, resize.disk_id)
        self.assertEqual(p.number, resize.partition_number)
        self.assertTrue(isinstance(resize, GuidedStorageTargetResize))
        self.assertEqual(0, len(resp.possible))

    @parameterized.expand(bootloaders_and_ptables)
    async def test_used_full_disk(self, bootloader, ptable):
        self._setup(bootloader, ptable)
        p = make_partition(self.model, self.disk, preserve=True,
                           size=gaps.largest_gap_size(self.disk))
        self.fs_probe[p._path()] = {'ESTIMATED_MIN_SIZE': 1 << 20}
        resp = await self.fsc.v2_guided_GET()
        reformat = resp.possible.pop(0)
        self.assertEqual(
            GuidedStorageTargetReformat(
                disk_id=self.disk.id, capabilities=default_capabilities),
            reformat)

        resize = resp.possible.pop(0)
        self.assertEqual(self.disk.id, resize.disk_id)
        self.assertEqual(p.number, resize.partition_number)
        self.assertTrue(isinstance(resize, GuidedStorageTargetResize))
        self.assertEqual(0, len(resp.possible))

    @parameterized.expand(bootloaders_and_ptables)
    async def test_weighted_split(self, bootloader, ptable):
        self._setup(bootloader, ptable, size=250 << 30)
        # add an extra, filler, partition so that there is no use_gap result
        make_partition(self.model, self.disk, preserve=True, size=9 << 30)
        p = make_partition(self.model, self.disk, preserve=True,
                           size=240 << 30)
        self.fs_probe[p._path()] = {'ESTIMATED_MIN_SIZE': 40 << 30}
        self.fsc.calculate_suggested_install_min.return_value = 10 << 30
        resp = await self.fsc.v2_guided_GET()
        reformat = resp.possible.pop(0)
        self.assertEqual(
            GuidedStorageTargetReformat(
                disk_id=self.disk.id, capabilities=default_capabilities),
            reformat)

        resize = resp.possible.pop(0)
        expected = GuidedStorageTargetResize(
            disk_id=self.disk.id,
            partition_number=p.number,
            new_size=200 << 30,
            minimum=50 << 30,
            recommended=200 << 30,
            maximum=230 << 30,
            capabilities=default_capabilities)
        self.assertEqual(expected, resize)
        self.assertEqual(0, len(resp.possible))

    @parameterized.expand(bootloaders_and_ptables)
    async def test_half_disk_reformat(self, bootloader, ptable):
        self._setup(bootloader, ptable, size=100 << 30)
        p = make_partition(self.model, self.disk, preserve=True, size=50 << 30)
        self.fs_probe[p._path()] = {'ESTIMATED_MIN_SIZE': 1 << 20}

        guided_get_resp = await self.fsc.v2_guided_GET()
        reformat = guided_get_resp.possible.pop(0)
        self.assertTrue(isinstance(reformat, GuidedStorageTargetReformat))

        use_gap = guided_get_resp.possible.pop(0)
        self.assertTrue(isinstance(use_gap, GuidedStorageTargetUseGap))

        resize = guided_get_resp.possible.pop(0)
        self.assertTrue(isinstance(resize, GuidedStorageTargetResize))

        data = GuidedChoiceV2(
            target=reformat, capability=GuidedCapability.DIRECT)
        expected_config = copy.copy(data)
        resp = await self.fsc.v2_guided_POST(data=data)
        self.assertEqual(expected_config, resp.configured)

        resp = await self.fsc.v2_GET()
        self.assertFalse(resp.need_root)
        self.assertFalse(resp.need_boot)
        self.assertEqual(0, len(guided_get_resp.possible))

    @parameterized.expand(bootloaders_and_ptables)
    async def test_half_disk_use_gap(self, bootloader, ptable):
        self._setup(bootloader, ptable, size=100 << 30)
        p = make_partition(self.model, self.disk, preserve=True, size=50 << 30)
        self.fs_probe[p._path()] = {'ESTIMATED_MIN_SIZE': 1 << 20}

        resp = await self.fsc.v2_GET()
        [orig_p, g] = resp.disks[0].partitions[-2:]

        guided_get_resp = await self.fsc.v2_guided_GET()
        reformat = guided_get_resp.possible.pop(0)
        self.assertTrue(isinstance(reformat, GuidedStorageTargetReformat))

        use_gap = guided_get_resp.possible.pop(0)
        self.assertTrue(isinstance(use_gap, GuidedStorageTargetUseGap))
        self.assertEqual(g, use_gap.gap)
        data = GuidedChoiceV2(
            target=use_gap, capability=GuidedCapability.DIRECT)
        expected_config = copy.copy(data)
        resp = await self.fsc.v2_guided_POST(data=data)
        self.assertEqual(expected_config, resp.configured)

        resize = guided_get_resp.possible.pop(0)
        self.assertTrue(isinstance(resize, GuidedStorageTargetResize))

        resp = await self.fsc.v2_GET()
        existing_part = [p for p in resp.disks[0].partitions
                         if getattr(p, 'number', None) == orig_p.number][0]
        self.assertEqual(orig_p, existing_part)
        self.assertFalse(resp.need_root)
        self.assertFalse(resp.need_boot)
        self.assertEqual(0, len(guided_get_resp.possible))

    @parameterized.expand(bootloaders_and_ptables)
    async def test_half_disk_resize(self, bootloader, ptable):
        self._setup(bootloader, ptable, size=100 << 30)
        p = make_partition(self.model, self.disk, preserve=True, size=50 << 30)
        self.fs_probe[p._path()] = {'ESTIMATED_MIN_SIZE': 1 << 20}

        resp = await self.fsc.v2_GET()
        [orig_p, g] = resp.disks[0].partitions[-2:]

        guided_get_resp = await self.fsc.v2_guided_GET()
        reformat = guided_get_resp.possible.pop(0)
        self.assertTrue(isinstance(reformat, GuidedStorageTargetReformat))

        use_gap = guided_get_resp.possible.pop(0)
        self.assertTrue(isinstance(use_gap, GuidedStorageTargetUseGap))

        resize = guided_get_resp.possible.pop(0)
        self.assertTrue(isinstance(resize, GuidedStorageTargetResize))
        p_expected = copy.copy(orig_p)
        p_expected.size = resize.new_size = 20 << 30
        p_expected.resize = True
        data = GuidedChoiceV2(
            target=resize, capability=GuidedCapability.DIRECT)
        expected_config = copy.copy(data)
        resp = await self.fsc.v2_guided_POST(data=data)
        self.assertEqual(expected_config, resp.configured)

        resp = await self.fsc.v2_GET()
        existing_part = [p for p in resp.disks[0].partitions
                         if getattr(p, 'number', None) == orig_p.number][0]
        self.assertEqual(p_expected, existing_part)
        self.assertFalse(resp.need_root)
        self.assertFalse(resp.need_boot)
        self.assertEqual(0, len(guided_get_resp.possible))

    @parameterized.expand([
        [10], [20], [25], [30], [50], [100], [250],
        [1000], [1024],
    ])
    async def test_lvm_20G_bad_offset(self, disk_size):
        disk_size = disk_size << 30
        self._setup(Bootloader.BIOS, 'gpt', size=disk_size)

        guided_get_resp = await self.fsc.v2_guided_GET()

        reformat = guided_get_resp.possible.pop(0)
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
            self.assertEqual(
                    parts[i + 1].offset, parts[i].offset + parts[i].size)
        self.assertEqual(
                disk_size - (1 << 20), parts[-1].offset + parts[-1].size,
                disk_size)

    async def _sizing_setup(self, bootloader, ptable, disk_size, policy):
        self._setup(bootloader, ptable, size=disk_size)

        resp = await self.fsc.v2_guided_GET()
        reformat = [target for target in resp.possible
                    if isinstance(target, GuidedStorageTargetReformat)][0]
        data = GuidedChoiceV2(target=reformat,
                              capability=GuidedCapability.LVM,
                              sizing_policy=policy)
        await self.fsc.v2_guided_POST(data=data)
        resp = await self.fsc.GET()

        [vg] = matching_dicts(resp.config, type='lvm_volgroup')
        [part_id] = vg['devices']
        [part] = matching_dicts(resp.config, id=part_id)
        part_size = part['size']  # already an int
        [lvm_partition] = matching_dicts(resp.config, type='lvm_partition')
        size = dehumanize_size(lvm_partition['size'])
        return size, part_size

    @parameterized.expand(bootloaders_and_ptables)
    async def test_scaled_disk(self, bootloader, ptable):
        size, part_size = await self._sizing_setup(
                bootloader, ptable, 50 << 30, SizingPolicy.SCALED)
        # expected to be about half, differing by boot and ptable types
        self.assertLess(20 << 30, size)
        self.assertLess(size, 30 << 30)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_unscaled_disk(self, bootloader, ptable):
        size, part_size = await self._sizing_setup(
                bootloader, ptable, 50 << 30, SizingPolicy.ALL)
        # there is some subtle differences in sizing depending on
        # ptable/bootloader and how the rounding goes
        self.assertLess(part_size - (5 << 20), size)
        self.assertLess(size, part_size)
        # but we should using most of the disk, minus boot partition(s)
        self.assertLess(45 << 30, size)


class TestManualBoot(IsolatedAsyncioTestCase):
    def _setup(self, bootloader, ptable, **kw):
        self.app = make_app()
        self.app.opts.bootloader = bootloader.value
        self.fsc = FilesystemController(app=self.app)
        self.fsc.model = self.model = make_model(bootloader)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_get_boot_disks_only(self, bootloader, ptable):
        self._setup(bootloader, ptable)
        disk = make_disk(self.model)
        self.assertEqual([disk.id],
                         await self.fsc.v2_potential_boot_disks_GET())

    @parameterized.expand(bootloaders_and_ptables)
    async def test_get_boot_disks_none(self, bootloader, ptable):
        self._setup(bootloader, ptable)
        self.assertEqual([], await self.fsc.v2_potential_boot_disks_GET())

    @parameterized.expand(bootloaders_and_ptables)
    async def test_get_boot_disks_all(self, bootloader, ptable):
        self._setup(bootloader, ptable)
        d1 = make_disk(self.model)
        d2 = make_disk(self.model)
        self.assertEqual(set([d1.id, d2.id]),
                         set(await self.fsc.v2_potential_boot_disks_GET()))

    @parameterized.expand(bootloaders_and_ptables)
    async def test_get_boot_disks_some(self, bootloader, ptable):
        self._setup(bootloader, ptable)
        d1 = make_disk(self.model)
        d2 = make_disk(self.model)
        make_partition(self.model, d1,
                       size=gaps.largest_gap_size(d1),
                       preserve=True)
        if bootloader == Bootloader.NONE:
            # NONE will always pass the boot check, even on a full disk
            expected = set([d1.id, d2.id])
        else:
            expected = set([d2.id])
        self.assertEqual(expected,
                         set(await self.fsc.v2_potential_boot_disks_GET()))


class TestCoreBootInstallMethods(IsolatedAsyncioTestCase):

    def setUp(self):
        self.app = make_app()
        self.app.command_runner = mock.AsyncMock()
        self.app.opts.bootloader = 'UEFI'
        self.app.report_start_event = mock.Mock()
        self.app.report_finish_event = mock.Mock()
        self.app.prober = mock.Mock()
        self.app.snapdapi = snapdapi.make_api_client(
            AsyncSnapd(get_fake_connection()))
        self.app.dr_cfg = DRConfig()
        self.app.dr_cfg.systems_dir_exists = True
        self.app.controllers.Source.get_handler.return_value = \
            TrivialSourceHandler('')
        self.fsc = FilesystemController(app=self.app)
        self.fsc._configured = True
        self.fsc.model = make_model(Bootloader.UEFI)

    def _add_details_for_structures(self, structures):
        system = self.fsc._system = snapdapi.SystemDetails(
            volumes={'pc': snapdapi.Volume(schema='gpt', structure=structures)}
            )
        [volume] = system.volumes.values()
        self.fsc._on_volume = snapdapi.OnVolume.from_volume(volume)

    async def test_guided_core_boot(self):
        disk = make_disk(self.fsc.model)
        arbitrary_uuid = str(uuid.uuid4())
        self._add_details_for_structures([
            snapdapi.VolumeStructure(
                type="83,0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                offset=1 << 20,
                size=1 << 30,
                filesystem='ext4',
                name='one'),
            snapdapi.VolumeStructure(
                type=arbitrary_uuid,
                offset=2 << 30,
                size=1 << 30,
                filesystem='ext4'),
            ])
        await self.fsc.guided_core_boot(disk)
        [part1, part2] = disk.partitions()
        self.assertEqual(part1.offset, 1 << 20)
        self.assertEqual(part1.size, 1 << 30)
        self.assertEqual(part1.fs().fstype, 'ext4')
        self.assertEqual(part1.flag, 'linux')
        self.assertEqual(part1.partition_name, 'one')
        self.assertEqual(
            part1.partition_type, '0FC63DAF-8483-4772-8E79-3D69D8477DE4')
        self.assertEqual(part2.flag, None)
        self.assertEqual(
            part2.partition_type, arbitrary_uuid)

    async def test_guided_core_boot_reuse(self):
        disk = make_disk(self.fsc.model)
        # Add a partition that matches one in the volume structure
        reused_part = make_partition(
            self.fsc.model, disk, offset=1 << 20, size=1 << 30, preserve=True)
        self.fsc.model.add_filesystem(reused_part, 'ext4')
        # And two that do not.
        make_partition(
            self.fsc.model, disk, offset=2 << 30, size=1 << 30, preserve=True)
        make_partition(
            self.fsc.model, disk, offset=3 << 30, size=1 << 30, preserve=True)
        self._add_details_for_structures([
            snapdapi.VolumeStructure(
                type="0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                offset=1 << 20,
                size=1 << 30,
                filesystem='ext4'),
            ])
        await self.fsc.guided_core_boot(disk)
        [part] = disk.partitions()
        self.assertEqual(reused_part, part)
        self.assertEqual(reused_part.wipe, 'superblock')
        self.assertEqual(part.fs().fstype, 'ext4')

    async def test_guided_core_boot_reuse_no_format(self):
        disk = make_disk(self.fsc.model)
        existing_part = make_partition(
            self.fsc.model, disk, offset=1 << 20, size=1 << 30, preserve=True)
        self._add_details_for_structures([
            snapdapi.VolumeStructure(
                type="0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                offset=1 << 20,
                size=1 << 30,
                filesystem=None),
            ])
        await self.fsc.guided_core_boot(disk)
        [part] = disk.partitions()
        self.assertEqual(existing_part, part)
        self.assertEqual(existing_part.wipe, None)

    async def test_guided_core_boot_system_data(self):
        disk = make_disk(self.fsc.model)
        self._add_details_for_structures([
            snapdapi.VolumeStructure(
                type="0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                offset=2 << 20,
                name='ptname',
                size=2 << 30,
                role=snapdapi.Role.SYSTEM_DATA,
                filesystem='ext4'),
            ])
        await self.fsc.guided_core_boot(disk)
        [part] = disk.partitions()
        self.assertEqual(part.offset, 2 << 20)
        self.assertEqual(part.partition_name, 'ptname')
        self.assertEqual(part.flag, 'linux')
        self.assertEqual(
            part.size,
            disk.size - (2 << 20) - disk.alignment_data().min_end_offset)
        self.assertEqual(part.fs().fstype, 'ext4')
        self.assertEqual(part.fs().mount().path, '/')
        self.assertEqual(part.wipe, 'superblock')

    async def test_from_sample_data(self):
        # calling this a unit test is definitely questionable. but it
        # runs much more quickly than the integration test!
        self.fsc.model = model = make_model(Bootloader.UEFI)
        disk = make_disk(model)
        self.app.base_model.source.current.snapd_system_label = \
            'prefer-encrypted'
        self.app.base_model.source.current.size = 1
        self.app.controllers.Source.source_path = ''

        self.app.dr_cfg.systems_dir_exists = True

        await self.fsc._get_system_task.start()
        self.fsc.start()

        response = await self.fsc.v2_guided_GET(wait=True)

        self.assertEqual(len(response.possible), 1)
        choice = GuidedChoiceV2(
            target=response.possible[0],
            capability=GuidedCapability.CORE_BOOT_ENCRYPTED)
        await self.fsc.v2_guided_POST(choice)

        self.assertEqual(model.storage_version, 2)

        partition_count = len([
            structure
            for structure in self.fsc._system.volumes['pc'].structure
            if structure.role != snapdapi.Role.MBR
            ])
        self.assertEqual(
            partition_count,
            len(disk.partitions()))
        mounts = {m.path: m.device.volume for m in model._all(type='mount')}
        self.assertEqual(set(mounts.keys()), {'/', '/boot', '/boot/efi'})
        device_map = {p.id: random_string() for p in disk.partitions()}
        self.fsc.update_devices(device_map)

        with mock.patch.object(snapdapi, "post_and_wait",
                               new_callable=mock.AsyncMock) as mocked:
            mocked.return_value = {
                'encrypted-devices': {
                    snapdapi.Role.SYSTEM_DATA: 'enc-system-data',
                    },
                }
            await self.fsc.setup_encryption(context=self.fsc.context)

        # setup_encryption mutates the filesystem model objects to
        # reference the newly created encrypted objects so re-read the
        # mount to device mapping.
        mounts = {m.path: m.device.volume for m in model._all(type='mount')}
        self.assertEqual(mounts['/'].path, 'enc-system-data')

        with mock.patch.object(snapdapi, "post_and_wait",
                               new_callable=mock.AsyncMock) as mocked:
            await self.fsc.finish_install(context=self.fsc.context)
        mocked.assert_called_once()
        [call] = mocked.mock_calls
        request = call.args[2]
        self.assertEqual(request.action, snapdapi.SystemAction.INSTALL)
        self.assertEqual(request.step, snapdapi.SystemActionStep.FINISH)
