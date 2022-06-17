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

from unittest import mock, TestCase

from parameterized import parameterized

from subiquity.server.controllers.filesystem import FilesystemController

from subiquitycore.tests.util import run_coro
from subiquitycore.tests.mocks import make_app
from subiquity.common.types import Bootloader
from subiquity.models.tests.test_filesystem import (
    make_disk,
    make_model,
    )


class TestSubiquityControllerFilesystem(TestCase):
    def setUp(self):
        self.app = make_app()
        self.app.opts.bootloader = 'UEFI'
        self.app.report_start_event = mock.Mock()
        self.app.report_finish_event = mock.Mock()
        self.app.prober = mock.Mock()
        self.fsc = FilesystemController(app=self.app)
        self.fsc._configured = True

    def test_probe_restricted(self):
        run_coro(self.fsc._probe_once(context=None, restricted=True))
        self.app.prober.get_storage.assert_called_with({'blockdev'})

    def test_probe_os_prober_false(self):
        self.app.opts.use_os_prober = False
        run_coro(self.fsc._probe_once(context=None, restricted=False))
        actual = self.app.prober.get_storage.call_args.args[0]
        self.assertTrue({'defaults'} <= actual)
        self.assertNotIn('os', actual)

    def test_probe_os_prober_true(self):
        self.app.opts.use_os_prober = True
        run_coro(self.fsc._probe_once(context=None, restricted=False))
        actual = self.app.prober.get_storage.call_args.args[0]
        self.assertTrue({'defaults', 'os'} <= actual)


class TestGuided(TestCase):
    def _guided_setup(self, bootloader, ptable):
        self.app = make_app()
        self.app.opts.bootloader = bootloader.value
        self.controller = FilesystemController(self.app)
        self.controller.model = make_model(bootloader)
        self.controller.model._probe_data = {'blockdev': {}}
        self.d1 = make_disk(self.controller.model, ptable=ptable)

    @parameterized.expand([
            (Bootloader.UEFI, 'gpt', '/boot/efi'),
            (Bootloader.UEFI, 'msdos', '/boot/efi'),
            (Bootloader.BIOS, 'gpt', None),
            # BIOS + msdos is different
            (Bootloader.PREP, 'gpt', None),
            (Bootloader.PREP, 'msdos', None),
        ])
    def test_guided_direct(self, bootloader, ptable, p1mnt):
        self._guided_setup(bootloader, ptable)
        self.controller.guided_direct(self.d1)
        [d1p1, d1p2] = self.d1.partitions()
        self.assertEqual(p1mnt, d1p1.mount)
        self.assertEqual('/', d1p2.mount)
        self.assertEqual(d1p1.size + d1p1.offset, d1p2.offset)

    def test_guided_direct_BIOS_MSDOS(self):
        self._guided_setup(Bootloader.BIOS, 'msdos')
        self.controller.guided_direct(self.d1)
        [d1p1] = self.d1.partitions()
        self.assertEqual('/', d1p1.mount)

    @parameterized.expand([
            (Bootloader.UEFI, 'gpt', '/boot/efi'),
            (Bootloader.UEFI, 'msdos', '/boot/efi'),
            (Bootloader.BIOS, 'gpt', None),
            # BIOS + msdos is different
            (Bootloader.PREP, 'gpt', None),
            (Bootloader.PREP, 'msdos', None),
        ])
    def test_guided_lvm(self, bootloader, ptable, p1mnt):
        self._guided_setup(bootloader, ptable)
        self.controller.guided_lvm(self.d1)
        [d1p1, d1p2, d1p3] = self.d1.partitions()
        self.assertEqual(p1mnt, d1p1.mount)
        self.assertEqual('/boot', d1p2.mount)
        self.assertEqual(None, d1p3.mount)
        self.assertEqual(d1p1.size + d1p1.offset, d1p2.offset)
        self.assertEqual(d1p2.size + d1p2.offset, d1p3.offset)

    def test_guided_lvm_BIOS_MSDOS(self):
        self._guided_setup(Bootloader.BIOS, 'msdos')
        self.controller.guided_lvm(self.d1)
        [d1p1, d1p2] = self.d1.partitions()
        self.assertEqual('/boot', d1p1.mount)
        self.assertEqual(None, d1p2.mount)
        self.assertEqual(d1p1.size + d1p1.offset, d1p2.offset)


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
