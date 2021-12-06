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

import datetime
import os
import shutil
import tempfile

from curtin.config import merge_config
from curtin.util import write_file

import yaml

from subiquitycore.lsb_release import lsb_release
from subiquitycore.utils import arun_command

from subiquity.server.curtin import run_curtin_command


class _MountBase:

    def p(self, *args):
        for a in args:
            if a.startswith('/'):
                raise Exception('no absolute paths here please')
        return os.path.join(self.mountpoint, *args)

    def write(self, path, content):
        with open(self.p(path), 'w') as fp:
            fp.write(content)


class Mountpoint(_MountBase):
    def __init__(self, *, mountpoint):
        self.mountpoint = mountpoint


class OverlayMountpoint(_MountBase):
    def __init__(self, *, lowers, upperdir, mountpoint):
        self.lowers = lowers
        self.upperdir = upperdir
        self.mountpoint = mountpoint


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

    def __init__(self, app, source):
        self.app = app
        self.source = source
        self.configured_tree = None
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

    async def unmount(self, mountpoint):
        await self.app.command_runner.run(['umount', mountpoint])

    async def setup_overlay(self, lowers):
        tdir = self.tdir()
        target = f'{tdir}/mount'
        workdir = f'{tdir}/work'
        upperdir = f'{tdir}/upper'
        for d in target, workdir, upperdir:
            os.mkdir(d)

        def lowerdir_for(lower):
            if isinstance(lower, str):
                return lower
            if isinstance(lower, Mountpoint):
                return lower.p()
            if isinstance(lower, OverlayMountpoint):
                return lowerdir_for(lower.lowers)
            if isinstance(lower, list):
                return ':'.join(reversed([lowerdir_for(ll) for ll in lower]))
            raise Exception(f'lowerdir_for({lower!r})')

        lowerdir = lowerdir_for(lowers)
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
        self.configured_tree = await self.setup_overlay(self.source)

        config_location = os.path.join(
            self.app.root, 'var/log/installer/subiquity-curtin-apt.conf')

        datestr = '# Autogenerated by Subiquity: {} UTC\n'.format(
            str(datetime.datetime.utcnow()))
        write_file(config_location, datestr + yaml.dump(self.apt_config()))

        self.app.note_data_for_apport("CurtinAptConfig", config_location)

        await run_curtin_command(
            self.app, context, 'apt-config', '-t', self.configured_tree.p(),
            config=config_location)

    async def configure_for_install(self, context):
        assert self.configured_tree is not None

        self.install_tree = await self.setup_overlay(self.configured_tree)

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

        codename = lsb_release()['codename']

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

    async def deconfigure(self, context, target):
        target = Mountpoint(mountpoint=target)

        await self.unmount(target.p('cdrom'))
        os.rmdir(target.p('cdrom'))

        restore_dirs = ['etc/apt']
        if not self.app.base_model.network.has_network:
            restore_dirs.append('var/lib/apt/lists')
        for dir in restore_dirs:
            shutil.rmtree(target.p(dir))
            await self.app.command_runner.run([
                'cp', '-aT', self.configured_tree.p(dir), target.p(dir),
                ])

        if self.app.base_model.network.has_network:
            await run_curtin_command(
                self.app, context, "in-target", "-t", target.p(),
                "--", "apt-get", "update")

        await self.cleanup()

        if self.app.base_model.network.has_network:
            await run_curtin_command(
                self.app, context, "in-target", "-t", target.p(),
                "--", "apt-get", "update")


class DryRunAptConfigurer(AptConfigurer):

    async def setup_overlay(self, source):
        if isinstance(source, OverlayMountpoint):
            source = source.lowers[0]
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


def get_apt_configurer(app, source):
    if app.opts.dry_run:
        return DryRunAptConfigurer(app, source)
    else:
        return AptConfigurer(app, source)
