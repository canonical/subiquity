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

import asyncio
import contextlib
import io
import logging
import os
import pathlib
import shutil
import subprocess
from typing import Optional

from curtin.config import merge_config

from subiquitycore.file_util import write_file, generate_config_yaml
from subiquitycore.lsb_release import lsb_release
from subiquitycore.utils import astart_command

from subiquity.server.curtin import run_curtin_command
from subiquity.server.mounter import (
    DryRunMounter,
    Mounter,
    Mountpoint,
    OverlayCleanupError,
    OverlayMountpoint,
    )

log = logging.getLogger('subiquity.server.apt')


class AptConfigCheckError(Exception):
    """ Error to raise when apt-get update fails with the currently applied
    configuration. """


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

    def __init__(self, app, mounter: Mounter, source: str):
        self.app = app
        self.mounter = mounter
        self.source: str = source
        self.configured_tree: Optional[OverlayMountpoint] = None
        self.install_tree: Optional[OverlayMountpoint] = None
        self.install_mount = None

    def apt_config(self):
        cfg = {}
        merge_config(cfg, self.app.base_model.mirror.get_apt_config())
        merge_config(cfg, self.app.base_model.proxy.get_apt_config())
        return {'apt': cfg}

    async def apply_apt_config(self, context):
        self.configured_tree = await self.mounter.setup_overlay([self.source])

        config_location = os.path.join(
            self.app.root, 'var/log/installer/subiquity-curtin-apt.conf')
        generate_config_yaml(config_location, self.apt_config())
        self.app.note_data_for_apport("CurtinAptConfig", config_location)

        await run_curtin_command(
            self.app, context, 'apt-config', '-t', self.configured_tree.p(),
            config=config_location, private_mounts=True)

    async def run_apt_config_check(self, output: io.StringIO) -> None:
        """ Run apt-get update (with various options limiting the amount of
        data donwloaded) in the overlay where the apt configuration was
        previously deployed. The output of apt-get (stdout + stderr) will be
        written to the output parameter.
        Raises a AptConfigCheckError exception if the apt-get command exited
        with non-zero. """
        assert self.configured_tree is not None

        pfx = pathlib.Path(self.configured_tree.p())

        apt_dirs = {
            "Etc::SourceList": pfx / "etc/apt/sources.list",
            "Etc::SourceParts": pfx / "etc/apt/sources.list.d",
            "Etc::Main": pfx / "etc/apt/apt.conf",
            "Etc::Parts": pfx / "etc/apt/apt.conf.d",
            "Etc::Preferences": pfx / "etc/apt/preferences",
            "Etc::PreferencesParts": pfx / "etc/apt/preferences.d",
            "Cache::Archives": pfx / "var/lib/apt/archives",
            "State::Lists": pfx / "var/lib/apt/lists",
            "Cache::PkgCache": None,
            "Cache::SrcPkgCache": None,
        }

        # Need to ensure the "partial" directory exists.
        partial_dir = apt_dirs["State::Lists"] / "partial"
        partial_dir.mkdir(
                parents=True, exist_ok=True)
        try:
            shutil.chown(partial_dir, user="_apt")
        except (PermissionError, LookupError) as exc:
            log.warning("could to set owner of file %s: %r", partial_dir, exc)

        disabled_downloads = [
                "deb::Packages",
                "deb::Translations",
                "deb::DEP-11",
                "deb::Contents-deb",
                "deb::Contents-udeb",
                "deb::Contents-deb-legacy",
                "deb::DEP-11-icons",
                "deb::DEP-11-icons-small",
                "deb::DEP-11-icons-large",
                "deb::DEP-11-icons-large-hidpi",
                ]

        apt_cmd = ["apt-get", "update", "-oAPT::Update::Error-Mode=any"]

        for key, path in apt_dirs.items():
            value = "" if path is None else str(path)
            apt_cmd.append(f"-oDir::{key}={str(value)}")

        for target in disabled_downloads:
            apt_cmd.append(
                    f"-oAcquire::IndexTargets::{target}::DefaultEnabled=false")


        proc = await astart_command(apt_cmd, stderr=subprocess.STDOUT)

        async def _reader():
            while not proc.stdout.at_eof():
                try:
                    line = await proc.stdout.readline()
                except asyncio.IncompleteReadError as e:
                    line = e.partial
                    if not line:
                        return
                output.write(line.decode("utf-8"))

        reader = asyncio.create_task(_reader())
        unused, returncode = await asyncio.gather(reader, proc.wait())

        if returncode != 0:
            raise AptConfigCheckError

    async def configure_for_install(self, context):
        assert self.configured_tree is not None

        self.install_tree = await self.mounter.setup_overlay(
            [self.configured_tree])

        os.mkdir(self.install_tree.p('cdrom'))
        await self.mounter.mount(
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
            "--", "apt-get", "update", private_mounts=True)

        return self.install_tree.p()

    @contextlib.asynccontextmanager
    async def overlay(self):
        overlay = await self.mounter.setup_overlay([
                self.install_tree.upperdir,
                self.configured_tree.upperdir,
                self.source
            ])
        try:
            yield overlay
        finally:
            # TODO self.unmount expects a Mountpoint object. Unfortunately, the
            # one we created in setup_overlay was discarded and replaced by an
            # OverlayMountPoint object instead. Here we re-create a new
            # Mountpoint object and (thanks to attr.s) make sure that it
            # compares equal to the one we discarded earlier.
            # But really, there should be better ways to handle this.
            try:
                await self.mounter.unmount(
                    Mountpoint(mountpoint=overlay.mountpoint))
            except subprocess.CalledProcessError as exc:
                raise OverlayCleanupError from exc

    async def cleanup(self):
        await self.mounter.cleanup()

    async def deconfigure(self, context, target: str) -> None:
        target_mnt = Mountpoint(mountpoint=target)

        async def _restore_dir(dir):
            shutil.rmtree(target_mnt.p(dir))
            await self.app.command_runner.run([
                'cp', '-aT', self.configured_tree.p(dir), target_mnt.p(dir),
                ])

        await _restore_dir('etc/apt')

        if self.app.base_model.network.has_network:
            await run_curtin_command(
                self.app, context, "in-target", "-t", target_mnt.p(),
                "--", "apt-get", "update", private_mounts=True)
        else:
            await _restore_dir('var/lib/apt/lists')

        await self.cleanup()
        try:
            d = target_mnt.p('cdrom')
            os.rmdir(d)
        except OSError as ose:
            log.warning(f'failed to rmdir {d}: {ose}')

    async def setup_target(self, context, target: str):
        # Call this after the rootfs has been extracted to the real target
        # system but before any configuration is applied to it.
        target_mnt = Mountpoint(mountpoint=target)
        await self.mounter.mount(
            '/cdrom', target_mnt.p('cdrom'), options='bind')


class DryRunAptConfigurer(AptConfigurer):

    @contextlib.asynccontextmanager
    async def overlay(self):
        yield await self.mounter.setup_overlay(self.install_tree.mountpoint)

    async def deconfigure(self, context, target):
        await self.cleanup()


def get_apt_configurer(app, source: str):
    if app.opts.dry_run:
        return DryRunAptConfigurer(app, DryRunMounter(app), source)
    else:
        return AptConfigurer(app, Mounter(app), source)
