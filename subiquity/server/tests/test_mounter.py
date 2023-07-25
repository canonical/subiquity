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

import os
import pathlib
from unittest.mock import AsyncMock, Mock, call, patch

from subiquity.server.mounter import (
    Mounter,
    Mountpoint,
    OverlayMountpoint,
    lowerdir_for,
)
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app


class TestMounter(SubiTestCase):
    def setUp(self):
        self.model = Mock()
        self.app = make_app(self.model)

    async def test_mount_unmount(self):
        mounter = Mounter(self.app)
        # Make sure we can unmount something that we mounted before.
        with patch.object(
            self.app, "command_runner", create=True, new_callable=AsyncMock
        ):
            m = await mounter.mount("/dev/cdrom", self.tmp_dir())
            await mounter.unmount(m)

    async def test_bind_mount_tree(self):
        mounter = Mounter(self.app)
        # bind_mount_tree bind-mounts files and directories from src
        # that are not already present into dst
        src = self.tmp_dir()
        dst = self.tmp_dir()

        def touch(*paths):
            for p in paths:
                if p.endswith("/"):
                    os.mkdir(p)
                else:
                    with open(p, "w"):
                        pass

        # Create the following situation:

        # src/                    dst/
        #     both-dir/               both-dir/
        #         both-file               both-file
        #                                 only-dst-file
        #         only-src-file
        #                             only-dst-dir/
        #                                 file
        #     only-src-dir/
        #         file
        #     only-src-file

        # We expect (only) these bind-mounts:
        #
        #   * src/both-dir/only-src-file -> dst/both-dir/only-src-file
        #   * src/only-src-dir           -> dst/only-src-dir
        #   * src/only-src-file          -> dst/only-src-file

        touch(f"{src}/only-src-file")
        touch(f"{dst}/only-dst-file")
        touch(f"{src}/both-file", f"{dst}/both-file")
        touch(f"{src}/only-src-dir/", f"{src}/only-src-dir/file")
        touch(f"{dst}/only-dst-dir/", f"{dst}/only-dst-dir/file")
        touch(f"{src}/both-dir/", f"{dst}/both-dir/")
        touch(f"{src}/both-dir/only-src-file", f"{src}/both-dir/both-file")
        touch(f"{dst}/both-dir/only-dst-file", f"{dst}/both-dir/both-file")

        with patch.object(mounter, "mount", new_callable=AsyncMock) as mocked:
            await mounter.bind_mount_tree(src, dst)
        mocked.assert_has_calls(
            [
                call(f"{src}/only-src-file", f"{dst}/only-src-file", options="bind"),
                call(f"{src}/only-src-dir", f"{dst}/only-src-dir", options="bind"),
                call(
                    f"{src}/both-dir/only-src-file",
                    f"{dst}/both-dir/only-src-file",
                    options="bind",
                ),
            ],
            any_order=True,
        )
        self.assertEqual(mocked.call_count, 3)

    async def test_bind_mount_tree_no_target(self):
        mounter = Mounter(self.app)
        # check bind_mount_tree behaviour when the passed dst does not
        # exist.
        src = self.tmp_dir()
        dst = os.path.join(self.tmp_dir(), "dst")

        with patch.object(mounter, "mount", new_callable=AsyncMock) as mocked:
            await mounter.bind_mount_tree(src, dst)
        mocked.assert_called_once_with(src, dst, options="bind")

    async def test_bind_mount_creates_dest_dir(self):
        mounter = Mounter(self.app)
        # When we are bind mounting a directory, the destination should be
        # created as a directory.
        src = self.tmp_dir()
        dst = pathlib.Path(self.tmp_dir()) / "dst"

        self.app.command_runner = AsyncMock()
        await mounter.bind_mount_tree(src, dst)
        self.assertTrue(dst.is_dir())

    async def test_bind_mount_file_creates_dest_file(self):
        mounter = Mounter(self.app)
        # When we are bind mounting a file, the destination should be created
        # as a file.
        src = pathlib.Path(self.tmp_dir()) / "src"
        src.touch()
        dst = pathlib.Path(self.tmp_dir()) / "dst"

        self.app.command_runner = AsyncMock()
        await mounter.bind_mount_tree(src, dst)
        self.assertTrue(dst.is_file())

    async def test_mount_file_creates_dest_dir(self):
        mounter = Mounter(self.app)
        # When we are mounting a device, the destination should be created
        # as a directory.
        src = pathlib.Path(self.tmp_dir()) / "src"
        src.touch()
        dst = pathlib.Path(self.tmp_dir()) / "dst"

        self.app.command_runner = AsyncMock()
        await mounter.mount(src, dst)
        self.assertTrue(dst.is_dir())


class TestLowerDirFor(SubiTestCase):
    def test_lowerdir_for_str(self):
        self.assertEqual(lowerdir_for("/tmp/lower1"), "/tmp/lower1")

    def test_lowerdir_for_str_list(self):
        self.assertEqual(
            lowerdir_for(["/tmp/lower1", "/tmp/lower2"]), "/tmp/lower2:/tmp/lower1"
        )

    def test_lowerdir_for_mountpoint(self):
        self.assertEqual(lowerdir_for(Mountpoint(mountpoint="/mnt")), "/mnt")

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
        self.assertEqual(lowerdir_for(overlay), "/tmp/upper1:/tmp/lower2:/tmp/lower1")

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
            "/tmp/lower2:/tmp/lower1"
            + ":/mnt/mountpoint"
            + ":/tmp/overlayupper1:/tmp/overlaylower2:/tmp/overlaylower1",
        )

    def test_lowerdir_for_other(self):
        with self.assertRaises(NotImplementedError):
            lowerdir_for(None)

        with self.assertRaises(NotImplementedError):
            lowerdir_for(10)
