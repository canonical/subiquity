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
import enum
import io
import logging
import os
import pathlib
import random
import re
import shutil
import subprocess
import tempfile
from typing import List, Optional

import apt_pkg
from curtin.commands.extract import AbstractSourceHandler
from curtin.config import merge_config

from subiquity.server.curtin import run_curtin_command
from subiquity.server.mounter import (
    DryRunMounter,
    Mounter,
    Mountpoint,
    OverlayCleanupError,
    OverlayMountpoint,
)
from subiquitycore.file_util import generate_config_yaml, write_file
from subiquitycore.lsb_release import lsb_release
from subiquitycore.utils import astart_command, orig_environ

log = logging.getLogger("subiquity.server.apt")


class AptConfigCheckError(Exception):
    """Error to raise when apt-get update fails with the currently applied
    configuration."""


def get_index_targets() -> List[str]:
    """Return the identifier of the data files that would be downloaded during
    apt-get update.
    NOTE: this uses the default configuration files from the host so this might
    slightly differ from what we would have in the overlay.
    Maybe we should run the following command in the overlay instead:
      $ apt-get indextargets --format '$(IDENTIFIER)' | sort -u
    """
    if "APT" not in apt_pkg.config:
        apt_pkg.init_config()
    targets = apt_pkg.config.keys("Acquire::IndexTargets")
    # Only return "top-level" identifiers such as:
    # Acquire::IndexTargets::deb::Contents-deb
    # Acquire::IndexTargets::deb-src::Sources
    return [key for key in targets if key.count("::") == 3]


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
    # 2. Copying a set of diverted /etc/apt files from the 'configured' overlay
    #    to the installed system. Some packages such as OEM meta-packages and
    #    keyrings will install files in /etc/apt so we cannot simply discard
    #    everything.
    #
    # 3. If the network is working, run apt-get update in the installed
    #    system, or if it is not, just copy /var/lib/apt/lists from the
    #    'configured_tree' overlay.

    def __init__(self, app, mounter: Mounter, source_handler: AbstractSourceHandler):
        self.app = app
        self.mounter = mounter
        self.source_handler: AbstractSourceHandler = source_handler
        self._source_path: Optional[str] = None
        self.configured_tree: Optional[OverlayMountpoint] = None
        self.install_tree: Optional[OverlayMountpoint] = None
        self.install_mount = None

    @property
    def source_path(self):
        if self._source_path is None:
            self._source_path = self.source_handler.setup()
        return self._source_path

    def apt_config(self, final: bool):
        cfg = {}
        has_network = self.app.base_model.network.has_network
        models = [
            self.app.base_model.mirror,
            self.app.base_model.proxy,
            self.app.base_model.debconf_selections,
        ]
        for model in models:
            merge_config(
                cfg, model.get_apt_config(final=final, has_network=has_network)
            )
        return {"apt": cfg}

    async def apply_apt_config(self, context, final: bool):
        self.configured_tree = await self.mounter.setup_overlay([self.source_path])

        config_location = os.path.join(
            self.app.root, "var/log/installer/subiquity-curtin-apt.conf"
        )
        generate_config_yaml(config_location, self.apt_config(final))
        self.app.note_data_for_apport("CurtinAptConfig", config_location)

        await run_curtin_command(
            self.app,
            context,
            "apt-config",
            "-t",
            self.configured_tree.p(),
            config=config_location,
            private_mounts=True,
        )

    async def run_apt_config_check(self, output: io.StringIO) -> None:
        """Run apt-get update (with various options limiting the amount of
        data donwloaded) in the overlay where the apt configuration was
        previously deployed. The output of apt-get (stdout + stderr) will be
        written to the output parameter.
        Raises a AptConfigCheckError exception if the apt-get command exited
        with non-zero."""
        assert self.configured_tree is not None

        pfx = pathlib.Path(self.configured_tree.p())

        apt_config = apt_pkg.Configuration()

        apt_dirs = {
            "Etc": pfx / "etc/apt",
            "Cache::Archives": pfx / "var/lib/apt/archives",
            "State::Lists": pfx / "var/lib/apt/lists",
            "Cache::PkgCache": None,
            "Cache::SrcPkgCache": None,
        }

        # Need to ensure the "partial" directory exists.
        partial_dir = apt_dirs["State::Lists"] / "partial"
        partial_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.chown(partial_dir, user="_apt")
        except (PermissionError, LookupError) as exc:
            log.warning("could to set owner of file %s: %r", partial_dir, exc)

        apt_cmd = [
            "apt-get",
            "update",
            "-oAPT::Update::Error-Mode=any",
            # Workaround because the default sandbox user (i.e., _apt) does not
            # have access to the overlay.
            "-oAPT::Sandbox::User=root",
        ]

        for key, path in apt_dirs.items():
            value = "" if path is None else str(path)
            apt_config[f"Dir::{key}"] = str(value)

        for target in get_index_targets():
            apt_cmd.append(f"-o{target}::DefaultEnabled=false")

        env = orig_environ(None)
        env["LANG"] = self.app.base_model.locale.selected_language
        with tempfile.NamedTemporaryFile(mode="w+") as config_file:
            env["APT_CONFIG"] = config_file.name
            config_file.write(apt_config.dump())
            config_file.flush()
            proc = await astart_command(
                apt_cmd, stderr=subprocess.STDOUT, clean_locale=False, env=env
            )

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

        self.install_tree = await self.mounter.setup_overlay([self.configured_tree])

        os.mkdir(self.install_tree.p("cdrom"))
        await self.mounter.mount("/cdrom", self.install_tree.p("cdrom"), options="bind")

        if self.app.base_model.network.has_network:
            os.rename(
                self.install_tree.p("etc/apt/sources.list"),
                self.install_tree.p("etc/apt/sources.list.d/original.list"),
            )
        else:
            proxy_path = self.install_tree.p("etc/apt/apt.conf.d/90curtin-aptproxy")
            if os.path.exists(proxy_path):
                os.unlink(proxy_path)

        codename = lsb_release(dry_run=self.app.opts.dry_run)["codename"]

        write_file(
            self.install_tree.p("etc/apt/sources.list"),
            f"deb [check-date=no] file:///cdrom {codename} main restricted\n",
        )

        await run_curtin_command(
            self.app,
            context,
            "in-target",
            "-t",
            self.install_tree.p(),
            "--",
            "apt-get",
            "update",
            private_mounts=True,
        )

        return self.install_tree.p()

    @contextlib.asynccontextmanager
    async def overlay(self):
        overlay = await self.mounter.setup_overlay(
            [
                self.install_tree.upperdir,
                self.configured_tree.upperdir,
                self.source_path,
            ]
        )
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
                await self.mounter.unmount(Mountpoint(mountpoint=overlay.mountpoint))
            except subprocess.CalledProcessError as exc:
                raise OverlayCleanupError from exc

    async def cleanup(self):
        # FIXME disabled until we can sort out umount
        # await self.mounter.cleanup()
        if self._source_path is not None:
            self.source_handler.cleanup()
            self._source_path = None

    async def deconfigure(self, context, target: str) -> None:
        target_mnt = Mountpoint(mountpoint=target)

        async def _restore_dir(dir):
            shutil.rmtree(target_mnt.p(dir))
            await self.app.command_runner.run(
                [
                    "cp",
                    "-aT",
                    self.configured_tree.p(dir),
                    target_mnt.p(dir),
                ]
            )

        def _restore_file(path: str) -> None:
            shutil.copyfile(self.configured_tree.p(path), target_mnt.p(path))

        # The file only exists if we are online
        with contextlib.suppress(FileNotFoundError):
            os.unlink(target_mnt.p("etc/apt/sources.list.d/original.list"))
        _restore_file("etc/apt/sources.list")

        with contextlib.suppress(FileNotFoundError):
            _restore_file("etc/apt/apt.conf.d/90curtin-aptproxy")

        if self.app.base_model.network.has_network:
            await run_curtin_command(
                self.app,
                context,
                "in-target",
                "-t",
                target_mnt.p(),
                "--",
                "apt-get",
                "update",
                private_mounts=True,
            )
        else:
            await _restore_dir("var/lib/apt/lists")

        await self.cleanup()
        try:
            d = target_mnt.p("cdrom")
            os.rmdir(d)
        except OSError as ose:
            log.warning(f"failed to rmdir {d}: {ose}")

    async def setup_target(self, context, target: str):
        # Call this after the rootfs has been extracted to the real target
        # system but before any configuration is applied to it.
        target_mnt = Mountpoint(mountpoint=target)
        await self.mounter.mount("/cdrom", target_mnt.p("cdrom"), options="bind")


class DryRunAptConfigurer(AptConfigurer):
    class MirrorCheckStrategy(enum.Enum):
        SUCCESS = "success"
        FAILURE = "failure"
        RANDOM = "random"

        RUN_ON_HOST = "run-on-host"

    @contextlib.asynccontextmanager
    async def overlay(self):
        yield await self.mounter.setup_overlay(self.install_tree.mountpoint)

    async def deconfigure(self, context, target):
        await self.cleanup()

    def get_mirror_check_strategy(self, url: str) -> "MirrorCheckStrategy":
        """For a given mirror URL, return the strategy that we should use to
        perform mirror checking."""
        for known in self.app.dr_cfg.apt_mirrors_known:
            if "url" in known:
                if known["url"] != url:
                    continue
            elif "pattern" in known:
                if not re.search(known["pattern"], url):
                    continue
            else:
                assert False

            return self.MirrorCheckStrategy(known["strategy"])

        return self.MirrorCheckStrategy(
            self.app.dr_cfg.apt_mirror_check_default_strategy
        )

    async def apt_config_check_failure(self, output: io.StringIO) -> None:
        """Pretend that the execution of the apt-get update command results in
        a failure."""
        url = self.app.base_model.mirror.primary_staged.uri
        release = lsb_release(dry_run=True)["codename"]
        host = url.split("/")[2]

        output.write(
            f"""\
Ign:1 {url} {release} InRelease
Ign:2 {url} {release}-updates InRelease
Ign:3 {url} {release}-backports InRelease
Ign:4 {url} {release}-security InRelease
Ign:2 {url} {release} InRelease
Ign:3 {url} {release}-updates InRelease
Err:1 {url} kinetic InRelease
 Temporary failure resolving '{host}'
Err:2 {url} kinetic-updates InRelease
 Temporary failure resolving '{host}'
Err:3 {url} kinetic-backports InRelease
 Temporary failure resolving '{host}'
Err:4 {url} kinetic-security InRelease
 Temporary failure resolving '{host}'
Reading package lists...
E: Failed to fetch {url}/dists/{release}/InRelease\
  Temporary failure resolving '{host}'
E: Failed to fetch {url}/dists/{release}-updates/InRelease\
  Temporary failure resolving '{host}'
E: Failed to fetch {url}/dists/{release}-backports/InRelease\
  Temporary failure resolving '{host}'
E: Failed to fetch {url}/dists/{release}-security/InRelease\
  Temporary failure resolving '{host}'
E: Some index files failed to download. They have been ignored,
 or old ones used instead.
"""
        )
        raise AptConfigCheckError

    async def apt_config_check_success(self, output: io.StringIO) -> None:
        """Pretend that the execution of the apt-get update command results in
        a success."""
        url = self.app.base_model.mirror.primary_staged.uri
        release = lsb_release(dry_run=True)["codename"]

        output.write(
            f"""\
Get:1 {url} {release} InRelease [267 kB]
Get:2 {url} {release}-updates InRelease [109 kB]
Get:3 {url} {release}-backports InRelease [99.9 kB]
Get:4 {url} {release}-security InRelease [109 kB]
Fetched 585 kB in 1s (1057 kB/s)
Reading package lists...
"""
        )

    async def run_apt_config_check(self, output: io.StringIO) -> None:
        """Dry-run implementation of the Apt config check.
        The strategy used is based on the URL of the primary mirror. The
        apt-get command can either run on the host or be faked entirely."""
        assert self.configured_tree is not None

        failure = self.apt_config_check_failure
        success = self.apt_config_check_success

        strategies = {
            self.MirrorCheckStrategy.RUN_ON_HOST: super().run_apt_config_check,
            self.MirrorCheckStrategy.FAILURE: failure,
            self.MirrorCheckStrategy.SUCCESS: success,
            self.MirrorCheckStrategy.RANDOM: random.choice([failure, success]),
        }
        mirror_url = self.app.base_model.mirror.primary_staged.uri

        strategy = strategies[self.get_mirror_check_strategy(mirror_url)]

        await strategy(output)


def get_apt_configurer(app, source: str):
    if app.opts.dry_run:
        return DryRunAptConfigurer(app, DryRunMounter(app), source)
    else:
        return AptConfigurer(app, Mounter(app), source)
