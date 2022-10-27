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

from unittest.mock import AsyncMock, Mock, patch

from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquity.server.mounter import (
    lowerdir_for,
    Mounter,
    Mountpoint,
    OverlayMountpoint,
)


class TestMounter(SubiTestCase):

    def setUp(self):
        self.model = Mock()
        self.app = make_app(self.model)

    async def test_mount_unmount(self):
        mounter = Mounter(self.app)
        # Make sure we can unmount something that we mounted before.
        with patch.object(self.app, "command_runner",
                          create=True, new_callable=AsyncMock):
            m = await mounter.mount("/dev/cdrom", "/target")
            await mounter.unmount(m)


class TestLowerDirFor(SubiTestCase):
    def test_lowerdir_for_str(self):
        self.assertEqual(
                lowerdir_for("/tmp/lower1"),
                "/tmp/lower1")

    def test_lowerdir_for_str_list(self):
        self.assertEqual(
                lowerdir_for(["/tmp/lower1", "/tmp/lower2"]),
                "/tmp/lower2:/tmp/lower1")

    def test_lowerdir_for_mountpoint(self):
        self.assertEqual(
                lowerdir_for(Mountpoint(mountpoint="/mnt")),
                "/mnt")

    def test_lowerdir_for_simple_overlay(self):
        overlay = OverlayMountpoint(
                lowers=["/tmp/lower1"],
                upperdir="/tmp/upper1",
                mountpoint="/mnt",
        )
        self.assertEqual(lowerdir_for(overlay), "/tmp/upper1:/tmp/lower1")

    def test_lowerdir_for_overlay(self):
        overlay = OverlayMountpoint(
                lowers=["/tmp/lower1", "/tmp/lower2"],
                upperdir="/tmp/upper1",
                mountpoint="/mnt",
        )
        self.assertEqual(
                lowerdir_for(overlay),
                "/tmp/upper1:/tmp/lower2:/tmp/lower1")

    def test_lowerdir_for_list(self):
        overlay = OverlayMountpoint(
                lowers=["/tmp/overlaylower1", "/tmp/overlaylower2"],
                upperdir="/tmp/overlayupper1",
                mountpoint="/mnt/overlay",
        )
        mountpoint = Mountpoint(mountpoint="/mnt/mountpoint")
        lowers = ["/tmp/lower1", "/tmp/lower2"]
        self.assertEqual(
                lowerdir_for([overlay, mountpoint, lowers]),
                "/tmp/lower2:/tmp/lower1" +
                ":/mnt/mountpoint" +
                ":/tmp/overlayupper1:/tmp/overlaylower2:/tmp/overlaylower1")

    def test_lowerdir_for_other(self):
        with self.assertRaises(NotImplementedError):
            lowerdir_for(None)

        with self.assertRaises(NotImplementedError):
            lowerdir_for(10)
