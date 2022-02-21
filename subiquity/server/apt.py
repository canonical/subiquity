# Copyright 2021 Canonical, Ltd.
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

import functools
import logging
import os
import shutil
import tempfile
from typing import List, Optional, Union

import attr

from curtin.config import merge_config

from subiquitycore.file_util import write_file, generate_config_yaml
from subiquitycore.lsb_release import lsb_release
from subiquitycore.utils import arun_command

from subiquity.server.curtin import run_curtin_command

log = logging.getLogger('subiquity.server.apt')


class _MountBase:

    def p(self, *args: str) -> str:
        for a in args:
            if a.startswith('/'):
                raise Exception('no absolute paths here please')
        return os.path.join(self.mountpoint, *args)

    def write(self, path, content):
        with open(self.p(path), 'w') as fp:
            fp.write(content)


@attr.s(auto_attribs=True, kw_only=True)
class Mountpoint(_MountBase):
    mountpoint: str


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
    return ':'.join(reversed([lowerdir_for(item) for item in lst]))


class AptConfigurer:
    # We configure apt during installation so that installs from the pool on
    # the cdrom are preferred during installation but remove this again in the
    # installed system.
    #
    # First we create an overlay ('configured_tree') over the installation
    # source and configure that overlay as we want the target system to end up
    # by running curtin's apt-config subcommand. This is done in the
    # apply_apt_config method.
    #
    # Then in configure_for_install we create a fresh overlay ('install_tree')
    # over the first one and configure it for the installation. This means:
    #
    # 1. Bind-mounting /cdrom into this new overlay.
    #
    # 2. When the network is expected to be working, copying the original
    #    /etc/apt/sources.list to /etc/apt/sources.list.d/original.list.
    #
    # 3. writing "deb file:///cdrom $(lsb_release -sc) main restricted"
    #    to /etc/apt/sources.list.
    #
    # 4. running "apt-get update" in the new overlay.
    #
    # When the install is done the deconfigure method makes the installed
    # system's apt state look as if the pool had never been configured. So
    # this means:
    #
    # 1. Removing /cdrom from the installed system.
    #
    # 2. Copying /etc/apt from the 'configured' overlay to the installed
    #    system.
    #
    # 3. If the network is working, run apt-get update in the installed
    #    system, or if it is not, just copy /var/lib/apt/lists from the
    #    'configured_tree' overlay.

    def __init__(self, app, source: str):
        self.app = app
        self.source: str = source
        self.configured_tree: Optional[OverlayMountpoint] = None
        self.install_tree: Optional[OverlayMountpoint] = None
        self.install_mount = None
        self._mounts = []
        self._tdirs = []

    def tdir(self):
        d = tempfile.mkdtemp()
        self._tdirs.append(d)
        return d

    async def mount(self, device, mountpoint, options=None, type=None):
        opts = []
        if options is not None:
            opts.extend(['-o', options])
        if type is not None:
            opts.extend(['-t', type])
        await self.app.command_runner.run(
            ['mount'] + opts + [device, mountpoint])
        m = Mountpoint(mountpoint=mountpoint)
        self._mounts.append(m)
        return m

    async def unmount(self, mountpoint: str):
        await self.app.command_runner.run(['umount', mountpoint])

    async def setup_overlay(self, lowers: List[Lower]) -> OverlayMountpoint:
        tdir = self.tdir()
        target = f'{tdir}/mount'
        lowerdir = lowerdir_for(lowers)
        upperdir = f'{tdir}/upper'
        workdir = f'{tdir}/work'
        for d in target, workdir, upperdir:
            os.mkdir(d)

        options = f'lowerdir={lowerdir},upperdir={upperdir},workdir={workdir}'

        mount = await self.mount(
            'overlay', target, options=options, type='overlay')

        return OverlayMountpoint(
            lowers=lowers,
            mountpoint=mount.p(),
            upperdir=upperdir)

    def apt_config(self):
        cfg = {}
        merge_config(cfg, self.app.base_model.mirror.get_apt_config())
        merge_config(cfg, self.app.base_model.proxy.get_apt_config())
        return {'apt': cfg}

    async def apply_apt_config(self, context):
        self.configured_tree = await self.setup_overlay([self.source])

        config_location = os.path.join(
            self.app.root, 'var/log/installer/subiquity-curtin-apt.conf')
        generate_config_yaml(config_location, self.apt_config())
        self.app.note_data_for_apport("CurtinAptConfig", config_location)

        await run_curtin_command(
            self.app, context, 'apt-config', '-t', self.configured_tree.p(),
            config=config_location)

    async def configure_for_install(self, context):
        assert self.configured_tree is not None

        self.install_tree = await self.setup_overlay([self.configured_tree])

        os.mkdir(self.install_tree.p('cdrom'))
        await self.mount(
            '/cdrom', self.install_tree.p('cdrom'), options='bind')

        if self.app.base_model.network.has_network:
            os.rename(
                self.install_tree.p('etc/apt/sources.list'),
                self.install_tree.p('etc/apt/sources.list.d/original.list'))
        else:
            proxy_path = self.install_tree.p(
                'etc/apt/apt.conf.d/90curtin-aptproxy')
            if os.path.exists(proxy_path):
                os.unlink(proxy_path)

        codename = lsb_release(dry_run=self.app.opts.dry_run)['codename']

        write_file(
            self.install_tree.p('etc/apt/sources.list'),
            f'deb [check-date=no] file:///cdrom {codename} main restricted\n')

        await run_curtin_command(
            self.app, context, "in-target", "-t", self.install_tree.p(),
            "--", "apt-get", "update")

        return self.install_tree.p()

    async def cleanup(self):
        for m in reversed(self._mounts):
            await self.unmount(m.mountpoint)
        for d in self._tdirs:
            shutil.rmtree(d)

    async def deconfigure(self, context, target: str) -> None:
        target_mnt = Mountpoint(mountpoint=target)

        async def _restore_dir(dir):
            shutil.rmtree(target_mnt.p(dir))
            await self.app.command_runner.run([
                'cp', '-aT', self.configured_tree.p(dir), target_mnt.p(dir),
                ])

        await self.unmount(target_mnt.p('cdrom'))
        os.rmdir(target_mnt.p('cdrom'))

        await _restore_dir('etc/apt')

        if self.app.base_model.network.has_network:
            await run_curtin_command(
                self.app, context, "in-target", "-t", target_mnt.p(),
                "--", "apt-get", "update")
        else:
            await _restore_dir('var/lib/apt/lists')

        await self.cleanup()

        if self.app.base_model.network.has_network:
            await run_curtin_command(
                self.app, context, "in-target", "-t", target_mnt.p(),
                "--", "apt-get", "update")


class DryRunAptConfigurer(AptConfigurer):

    async def setup_overlay(self, lowers: List[Lower]) -> OverlayMountpoint:
        # XXX This implementation expects that:
        # - on first invocation, the lowers list contains a single string
        # element.
        # - on second invocation, the lowers list contains the
        # OverlayMountPoint returned by the first invocation.
        lowerdir = lowers[0]
        if isinstance(lowerdir, OverlayMountpoint):
            source = lowerdir.lowers[0]
        else:
            source = lowerdir
        target = self.tdir()
        os.mkdir(f'{target}/etc')
        await arun_command([
            'cp', '-aT', f'{source}/etc/apt', f'{target}/etc/apt',
            ], check=True)
        if os.path.isdir(f'{target}/etc/apt/sources.list.d'):
            shutil.rmtree(f'{target}/etc/apt/sources.list.d')
        os.mkdir(f'{target}/etc/apt/sources.list.d')
        return OverlayMountpoint(
            lowers=[source],
            mountpoint=target,
            upperdir=None)

    async def deconfigure(self, context, target):
        return


def get_apt_configurer(app, source: str):
    if app.opts.dry_run:
        return DryRunAptConfigurer(app, source)
    else:
        return AptConfigurer(app, source)
