# Copyright 2024 Canonical, Ltd.
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
from unittest import mock

from subiquity.common.filesystem.boot import _can_be_boot_device_disk
from subiquity.models.tests.test_filesystem import make_model_and_disk
from subiquitycore.tests.parameterized import parameterized


class TestCanBeBootDevice(unittest.TestCase):
    @parameterized.expand(
        (
            (False, False, True),
            (False, True, True),
            (True, True, True),
            (True, False, False),
        )
    )
    def test__can_be_boot_device_disk(
        self,
        on_remote_storage: bool,
        supports_nvme_tcp_boot: bool,
        expect_can_be_boot_device: bool,
    ):
        model, disk = make_model_and_disk()

        model.opt_supports_nvme_tcp_booting = supports_nvme_tcp_boot

        p_on_remote_storage = mock.patch.object(
            disk, "on_remote_storage", return_value=on_remote_storage
        )
        p_get_boot_device_plan = mock.patch(
            "subiquity.common.filesystem.boot.get_boot_device_plan", return_value=True
        )

        with p_on_remote_storage, p_get_boot_device_plan as m_gbdp:
            self.assertEqual(expect_can_be_boot_device, _can_be_boot_device_disk(disk))

        if not on_remote_storage or supports_nvme_tcp_boot:
            m_gbdp.assert_called_once_with(disk, resize_partition=None)
        else:
            m_gbdp.assert_not_called()
