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

from collections import defaultdict
import unittest

from subiquity.controllers.filesystem import (
    FilesystemController,
    )
from subiquity.models.tests.test_filesystem import (
    make_model_and_disk,
    )
from subiquity.models.filesystem import (
    Bootloader,
    DeviceAction,
    )


class Thing:
    # Just something to hang attributes off
    pass


def make_controller_and_disk(bootloader=None):
    common = defaultdict(type(None))
    bm = Thing()
    bm.filesystem, disk = make_model_and_disk(bootloader)
    common['base_model'] = bm
    common['answers'] = {}
    opts = Thing()
    opts.dry_run = True
    opts.bootloader = None
    common['opts'] = opts
    controller = FilesystemController(common)
    return controller, disk


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

    def test_can_only_make_boot_once(self):
        # This is really testing model code but it's much easier to test with a
        # controller around.
        for bl in Bootloader:
            controller, disk = make_controller_and_disk(bl)
            if DeviceAction.MAKE_BOOT not in disk.supported_actions:
                continue
            controller.make_boot_disk(disk)
            self.assertFalse(
                disk._can_MAKE_BOOT,
                "make_boot_disk(disk) did not make _can_MAKE_BOOT false with "
                "bootloader {}".format(bl))
