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

import unittest
from unittest.mock import Mock

from subiquity.common.filesystem import boot
from subiquity.models.filesystem import Bootloader
from subiquity.models.tests.test_filesystem import make_model, make_raid


class TestBootDevRaid(unittest.TestCase):
    def test_bios(self):
        raid = make_raid(make_model(Bootloader.BIOS))
        self.assertFalse(boot.can_be_boot_device(raid))

    def test_UEFI_no_container(self):
        raid = make_raid(make_model(Bootloader.UEFI))
        raid.container = None
        self.assertFalse(boot.can_be_boot_device(raid))

    def test_UEFI_container_imsm(self):
        raid = make_raid(make_model(Bootloader.UEFI))
        raid.container = Mock()
        raid.container.metadata = "imsm"
        self.assertTrue(boot.can_be_boot_device(raid))

    def test_UEFI_container_non_imsm(self):
        raid = make_raid(make_model(Bootloader.UEFI))
        raid.container = Mock()
        raid.container.metadata = "something else"
        self.assertFalse(boot.can_be_boot_device(raid))
