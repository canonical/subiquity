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
import functools
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Union

import attr

from subiquitycore.utils import arun_command

log = logging.getLogger("subiquity.server.mounter")


class TmpFileSet:
    def __init__(self):
        self._tdirs: List[str] = []

    def tdir(self):
        d = tempfile.mkdtemp()
        self._tdirs.append(d)
        return d

    def cleanup(self):
        for d in self._tdirs[:]:
            try:
                shutil.rmtree(d)
                self._tdirs.remove(d)
            except OSError as ose:
                log.warning(f"failed to rmtree {d}: {ose}")


class OverlayCleanupError(Exception):
    """Exception to raise when an overlay could not be cleaned up."""


class _MountBase:
    def p(self, *args: str) -> str:
        for a in args:
            if a.startswith("/"):
                raise Exception("no absolute paths here please")
        return os.path.join(self.mountpoint, *args)

    def write(self, path, content):
        with open(self.p(path), "w") as fp:
            fp.write(content)


@attr.s(auto_attribs=True, kw_only=True)
class Mountpoint(_MountBase):
    mountpoint: str
    created: bool = False


@attr.s(auto_attribs=True, kw_only=True)
class OverlayMountpoint(_MountBase):
    # The first element in lowers will be the bottom layer and the last element
    # will be the top layer.
    lowers: List["Lower"]
    upperdir: Optional[str]
    mountpoint: str


Lower = Union[Mountpoint, str, OverlayMountpoint]


@functools.singledispatch
def lowerdir_for(x):
    """Return value suitable for passing to the lowerdir= overlayfs option."""
    raise NotImplementedError(x)


@lowerdir_for.register(str)
def _lowerdir_for_str(path):
    return path


@lowerdir_for.register(Mountpoint)
def _lowerdir_for_mnt(mnt):
    return mnt.mountpoint


@lowerdir_for.register(OverlayMountpoint)
def _lowerdir_for_ovmnt(ovmnt):
    # One cannot indefinitely stack overlayfses so construct an
    # explicit list of the layers of the overlayfs.
    return lowerdir_for([ovmnt.lowers, ovmnt.upperdir])


@lowerdir_for.register(list)
def _lowerdir_for_lst(lst):
    return ":".join(reversed([lowerdir_for(item) for item in lst]))


class Mounter:
    def __init__(self, app):
        self.app = app
        self.tmpfiles = TmpFileSet()
        self._mounts: List[Mountpoint] = []

    async def mount(self, device, mountpoint=None, options=None, type=None):
        opts = []
        if options is not None:
            opts.extend(["-o", options])
        if type is not None:
            opts.extend(["-t", type])
        if mountpoint is None:
            mountpoint = tempfile.mkdtemp()
            created = True
        elif os.path.exists(mountpoint):
            created = False
        else:
            path = Path(device)
            if options == "bind" and not path.is_dir():
                Path(mountpoint).touch(exist_ok=False)
            else:
                os.makedirs(mountpoint, exist_ok=False)
            created = True
        await self.app.command_runner.run(
            ["mount"] + opts + [device, mountpoint], private_mounts=False
        )
        m = Mountpoint(mountpoint=mountpoint, created=created)
        self._mounts.append(m)
        return m

    async def unmount(self, mountpoint: Mountpoint, remove=True):
        if remove:
            self._mounts.remove(mountpoint)
        await self.app.command_runner.run(
            ["umount", mountpoint.mountpoint], private_mounts=False
        )
        if mountpoint.created:
            path = Path(mountpoint.mountpoint)
            if path.is_dir():
                with contextlib.suppress(OSError):
                    path.rmdir()
            else:
                path.unlink(missing_ok=True)

    async def setup_overlay(self, lowers: List[Lower]) -> OverlayMountpoint:
        tdir = self.tmpfiles.tdir()
        target = f"{tdir}/mount"
        lowerdir = lowerdir_for(lowers)
        upperdir = f"{tdir}/upper"
        workdir = f"{tdir}/work"
        for d in target, workdir, upperdir:
            os.mkdir(d)

        options = f"lowerdir={lowerdir},upperdir={upperdir},workdir={workdir}"

        mount = await self.mount("overlay", target, options=options, type="overlay")

        return OverlayMountpoint(lowers=lowers, mountpoint=mount.p(), upperdir=upperdir)

    async def cleanup(self):
        for m in reversed(self._mounts):
            await self.unmount(m, remove=False)
        self.tmpfiles.cleanup()

    async def bind_mount_tree(self, src, dst):
        """bind-mount files and directories from src that are not already
        present into dst"""
        if not os.path.exists(dst):
            await self.mount(src, dst, options="bind")
            return
        for src_dirpath, dirnames, filenames in os.walk(src):
            dst_dirpath = src_dirpath.replace(src, dst)
            for name in dirnames + filenames:
                dst_path = os.path.join(dst_dirpath, name)
                if os.path.exists(dst_path):
                    continue
                src_path = os.path.join(src_dirpath, name)
                await self.mount(src_path, dst_path, options="bind")
                if name in dirnames:
                    dirnames.remove(name)

    @contextlib.asynccontextmanager
    async def mounted(self, device, mountpoint=None, options=None, type=None):
        mp = await self.mount(device, mountpoint, options, type)
        try:
            yield mp
        finally:
            await self.unmount(mp)


class DryRunMounter(Mounter):
    async def setup_overlay(self, lowers: List[Lower]) -> OverlayMountpoint:
        # XXX This implementation expects that:
        # - on first invocation, the lowers list contains a single string
        # element.
        # - on second invocation, the lowers list contains the
        # OverlayMountPoint returned by the first invocation.
        #
        # This is all very specific to the use of setup_overlay in
        # AptConfigurer. It would be nice to fix that somehow.
        lowerdir = lowers[0]
        if isinstance(lowerdir, OverlayMountpoint):
            source = lowerdir.lowers[0]
        else:
            source = lowerdir
        target = self.tmpfiles.tdir()
        os.mkdir(f"{target}/etc")
        await arun_command(
            [
                "cp",
                "-aT",
                f"{source}/etc/apt",
                f"{target}/etc/apt",
            ],
            check=True,
        )
        return OverlayMountpoint(lowers=[source], mountpoint=target, upperdir=None)
