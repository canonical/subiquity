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
from unittest import mock, TestCase, IsolatedAsyncioTestCase

from parameterized import parameterized

from subiquity.server.controllers.filesystem import FilesystemController

from subiquitycore.tests.mocks import make_app
from subiquity.common.filesystem import gaps
from subiquity.common.types import (
    Bootloader,
    GuidedChoiceV2,
    GuidedStorageTargetReformat,
    GuidedStorageTargetResize,
    GuidedStorageTargetUseGap,
    ProbeStatus,
    )
from subiquity.models.tests.test_filesystem import (
    make_disk,
    make_model,
    make_partition,
    )


bootloaders = [(bl, ) for bl in list(Bootloader)]
bootloaders_and_ptables = [(bl, pt)
                           for bl in list(Bootloader)
                           for pt in ('gpt', 'msdos', 'vtoc')]


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


class TestGuided(TestCase):
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
    def test_guided_direct(self, bootloader, ptable, p1mnt):
        self._guided_setup(bootloader, ptable)
        target = GuidedStorageTargetReformat(disk_id=self.d1.id)
        self.controller.guided(GuidedChoiceV2(target=target, use_lvm=False))
        [d1p1, d1p2] = self.d1.partitions()
        self.assertEqual(p1mnt, d1p1.mount)
        self.assertEqual('/', d1p2.mount)
        self.assertIsNone(gaps.largest_gap(self.d1))

    def test_guided_direct_BIOS_MSDOS(self):
        self._guided_setup(Bootloader.BIOS, 'msdos')
        target = GuidedStorageTargetReformat(disk_id=self.d1.id)
        self.controller.guided(GuidedChoiceV2(target=target, use_lvm=False))
        [d1p1] = self.d1.partitions()
        self.assertEqual('/', d1p1.mount)
        self.assertIsNone(gaps.largest_gap(self.d1))

    @parameterized.expand(boot_expectations)
    def test_guided_lvm(self, bootloader, ptable, p1mnt):
        self._guided_setup(bootloader, ptable)
        target = GuidedStorageTargetReformat(disk_id=self.d1.id)
        self.controller.guided(GuidedChoiceV2(target=target, use_lvm=True))
        [d1p1, d1p2, d1p3] = self.d1.partitions()
        self.assertEqual(p1mnt, d1p1.mount)
        self.assertEqual('/boot', d1p2.mount)
        self.assertEqual(None, d1p3.mount)
        [vg] = self.model._all(type='lvm_volgroup')
        [part] = list(vg.devices)
        self.assertEqual(d1p3, part)
        self.assertIsNone(gaps.largest_gap(self.d1))

    def test_guided_lvm_BIOS_MSDOS(self):
        self._guided_setup(Bootloader.BIOS, 'msdos')
        target = GuidedStorageTargetReformat(disk_id=self.d1.id)
        self.controller.guided(GuidedChoiceV2(target=target, use_lvm=True))
        [d1p1, d1p2] = self.d1.partitions()
        self.assertEqual('/boot', d1p1.mount)
        [vg] = self.model._all(type='lvm_volgroup')
        [part] = list(vg.devices)
        self.assertEqual(d1p2, part)
        self.assertEqual(None, d1p2.mount)
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
    def test_guided_direct_side_by_side(self, bl, pt, flag):
        self._guided_side_by_side(bl, pt)
        parts_before = self.d1._partitions.copy()
        gap = gaps.largest_gap(self.d1)
        target = GuidedStorageTargetUseGap(disk_id=self.d1.id, gap=gap)
        self.controller.guided(GuidedChoiceV2(target=target, use_lvm=False))
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
    def test_guided_lvm_side_by_side(self, bl, pt, flag):
        self._guided_side_by_side(bl, pt)
        parts_before = self.d1._partitions.copy()
        gap = gaps.largest_gap(self.d1)
        target = GuidedStorageTargetUseGap(disk_id=self.d1.id, gap=gap)
        self.controller.guided(GuidedChoiceV2(target=target, use_lvm=True))
        parts_after = gaps.parts_and_gaps(self.d1)[:-2]
        self.assertEqual(parts_before, parts_after)
        p_boot, p_data = gaps.parts_and_gaps(self.d1)[-2:]
        self.assertEqual('/boot', p_boot.mount)
        self.assertEqual(flag, p_boot.flag)
        self.assertEqual(None, p_data.mount)
        self.assertEqual(flag, p_data.flag)


class TestLayout(TestCase):
    def setUp(self):
        self.app = make_app()
        self.app.opts.bootloader = None
        self.fsc = FilesystemController(app=self.app)

    @parameterized.expand([('reformat_disk',), ('use_gap',)])
    def test_good_modes(self, mode):
        self.fsc.validate_layout_mode(mode)

    @parameterized.expand([('resize_biggest',), ('use_free',)])
    def test_bad_modes(self, mode):
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
        if bootloader == Bootloader.BIOS and ptable != 'msdos' and fix_bios:
            make_partition(self.model, self.disk, preserve=True,
                           flag='bios_grub', size=1 << 20, offset=1 << 20)

    @parameterized.expand(bootloaders_and_ptables)
    async def test_blank_disk(self, bootloader, ptable):
        # blank disks should not report a UseGap case
        self._setup(bootloader, ptable, fix_bios=False)
        expected = [GuidedStorageTargetReformat(disk_id=self.disk.id)]
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
        self.assertEqual(GuidedStorageTargetReformat(disk_id=self.disk.id),
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
        self.assertEqual(GuidedStorageTargetReformat(disk_id=self.disk.id),
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
        self.assertEqual(GuidedStorageTargetReformat(disk_id=self.disk.id),
                         reformat)

        resize = resp.possible.pop(0)
        expected = GuidedStorageTargetResize(
                disk_id=self.disk.id,
                partition_number=p.number,
                new_size=200 << 30,
                minimum=50 << 30,
                recommended=200 << 30,
                maximum=230 << 30)
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

        data = GuidedChoiceV2(target=reformat)
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
        data = GuidedChoiceV2(target=use_gap)
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
        data = GuidedChoiceV2(target=resize)
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
