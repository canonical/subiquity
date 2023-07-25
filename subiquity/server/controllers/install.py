# Copyright 2020 Canonical, Ltd.
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
import copy
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from curtin.config import merge_config
from curtin.util import get_efibootmgr, is_uefi_bootable

from subiquity.common.errorreport import ErrorReportKind
from subiquity.common.types import ApplicationState, PackageInstallState
from subiquity.journald import journald_listen
from subiquity.models.filesystem import ActionRenderMode
from subiquity.server.controller import SubiquityController
from subiquity.server.curtin import run_curtin_command, start_curtin_command
from subiquity.server.kernel import list_installed_kernels
from subiquity.server.mounter import Mounter
from subiquity.server.types import InstallerChannels
from subiquitycore.async_helpers import run_bg_task, run_in_thread
from subiquitycore.context import with_context
from subiquitycore.file_util import (
    generate_config_yaml,
    generate_timestamped_header,
    write_file,
)
from subiquitycore.utils import arun_command, log_process_streams

log = logging.getLogger("subiquity.server.controllers.install")


class TracebackExtractor:
    start_marker = re.compile(r"^Traceback \(most recent call last\):")
    end_marker = re.compile(r"\S")

    def __init__(self):
        self.traceback = []
        self.in_traceback = False

    def feed(self, line):
        if not self.traceback and self.start_marker.match(line):
            self.in_traceback = True
        elif self.in_traceback and self.end_marker.match(line):
            self.traceback.append(line)
            self.in_traceback = False
        if self.in_traceback:
            self.traceback.append(line)


class InstallController(SubiquityController):
    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model

        self.unattended_upgrades_cmd = None
        self.unattended_upgrades_ctx = None
        self.tb_extractor = TracebackExtractor()

    def interactive(self):
        return True

    def stop_uu(self):
        if self.app.state == ApplicationState.UU_RUNNING:
            self.app.update_state(ApplicationState.UU_CANCELLING)
            run_bg_task(self.stop_unattended_upgrades())

    def start(self):
        journald_listen([self.app.log_syslog_id], self.log_event)
        self.install_task = asyncio.create_task(self.install())

    def tpath(self, *path):
        return os.path.join(self.model.target, *path)

    def log_event(self, event):
        self.tb_extractor.feed(event["MESSAGE"])

    def write_config(self, config_file: Path, config: Any) -> None:
        """Create a YAML file that represents the curtin install configuration
        specified."""
        config_file.parent.mkdir(parents=True, exist_ok=True)
        generate_config_yaml(str(config_file), config)

    def base_config(self, logs_dir, resume_data_file) -> Dict[str, Any]:
        """Return configuration to be used as part of every curtin install
        step."""
        return {
            "install": {
                "target": self.model.target,
                "unmount": "disabled",
                "save_install_config": False,
                "save_install_log": False,
                "log_file": str(logs_dir / "curtin-install.log"),
                "log_file_append": True,
                "error_tarfile": str(logs_dir / "curtin-errors.tar"),
                "resume_data": str(resume_data_file),
            }
        }

    def filesystem_config(
        self,
        device_map_path: Path,
        mode: ActionRenderMode = ActionRenderMode.DEFAULT,
    ) -> Dict[str, Any]:
        """Return configuration to be used as part of a curtin 'block-meta'
        step."""
        cfg = self.model.filesystem.render(mode=mode)
        if device_map_path is not None:
            cfg["storage"]["device_map_path"] = str(device_map_path)
        return cfg

    def generic_config(self, **kw) -> Dict[str, Any]:
        """Return configuration to be used as part of a generic curtin
        install step."""
        config = self.model.render()
        config.update(kw)
        return config

    def rp_config(self, logs_dir: Path, target: str) -> Dict[str, Any]:
        """Return configuration to be used as part of populating a recovery
        partition."""
        return {
            "install": {
                "target": target,
                "resume_data": None,
                "extra_rsync_args": ["--no-links"],
            }
        }

    @with_context(description="umounting /target dir")
    async def unmount_target(self, *, context, target):
        await run_curtin_command(
            self.app, context, "unmount", "-t", target, private_mounts=False
        )
        if not self.app.opts.dry_run:
            shutil.rmtree(target)

    def supports_apt(self) -> bool:
        return (
            self.model.target is not None
            and self.model.source.current.variant != "core"
        )

    @with_context(description="configuring apt", level="INFO", childlevel="DEBUG")
    async def configure_apt(self, *, context):
        mirror = self.app.controllers.Mirror
        fsc = self.app.controllers.Filesystem
        configurer = await mirror.wait_config(fsc._info.name)
        return await configurer.configure_for_install(context)

    async def setup_target(self, context):
        if not self.supports_apt():
            return
        mirror = self.app.controllers.Mirror
        await mirror.final_apt_configurer.setup_target(context, self.tpath())

    @with_context(description="executing curtin install {name} step")
    async def run_curtin_step(
        self,
        context,
        name: str,
        stages: List[str],
        config_file: Path,
        source: Optional[str],
        config: Dict[str, Any],
    ):
        """Run a curtin install step."""
        self.app.note_file_for_apport(
            f"Curtin{name.title().replace(' ', '')}Config", str(config_file)
        )

        self.write_config(config_file=config_file, config=config)

        log_file = Path(config["install"]["log_file"])

        # Make sure the log directory exists.
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Add a marker to identify the step in the log file.
        with open(str(log_file), mode="a") as fh:
            fh.write(f"\n---- [[ subiquity step {name} ]] ----\n")

        if source is not None:
            source_args = (source,)
        else:
            source_args = ()

        await run_curtin_command(
            self.app,
            context,
            "install",
            "--set",
            f"json:stages={json.dumps(stages)}",
            *source_args,
            config=str(config_file),
            private_mounts=False,
        )

        device_map_path = config.get("storage", {}).get("device_map_path")
        if device_map_path is not None:
            with open(device_map_path) as fp:
                device_map = json.load(fp)
            self.app.controllers.Filesystem.update_devices(device_map)

    @with_context(description="installing system", level="INFO", childlevel="DEBUG")
    async def curtin_install(self, *, context, source):
        if self.app.opts.dry_run:
            root = Path(self.app.opts.output_base)
        else:
            root = Path("/")

        logs_dir = root / "var/log/installer"

        config_dir = logs_dir / "curtin-install"

        base_config = self.base_config(
            logs_dir, Path(tempfile.mkdtemp()) / "resume-data.json"
        )

        self.app.note_file_for_apport(
            "CurtinErrors", base_config["install"]["error_tarfile"]
        )
        self.app.note_file_for_apport("CurtinLog", base_config["install"]["log_file"])

        fs_controller = self.app.controllers.Filesystem

        async def run_curtin_step(name, stages, step_config, source=None):
            config = copy.deepcopy(base_config)
            filename = f"subiquity-{name.replace(' ', '-')}.conf"
            merge_config(config, copy.deepcopy(step_config))
            await self.run_curtin_step(
                context=context,
                name=name,
                stages=stages,
                config_file=config_dir / filename,
                source=source,
                config=config,
            )

        await run_curtin_step(name="initial", stages=[], step_config={})

        if fs_controller.reset_partition_only:
            await run_curtin_step(
                name="partitioning",
                stages=["partitioning"],
                step_config=self.filesystem_config(
                    device_map_path=logs_dir / "device-map.json",
                ),
            )
        elif fs_controller.is_core_boot_classic():
            await run_curtin_step(
                name="partitioning",
                stages=["partitioning"],
                step_config=self.filesystem_config(
                    mode=ActionRenderMode.DEVICES,
                    device_map_path=logs_dir / "device-map-partition.json",
                ),
            )
            if fs_controller.use_tpm:
                await fs_controller.setup_encryption(context=context)
            await run_curtin_step(
                name="formatting",
                stages=["partitioning"],
                step_config=self.filesystem_config(
                    mode=ActionRenderMode.FORMAT_MOUNT,
                    device_map_path=logs_dir / "device-map-format.json",
                ),
            )
            await run_curtin_step(
                name="extract",
                stages=["extract"],
                step_config=self.generic_config(),
                source=source,
            )
            await self.create_core_boot_classic_fstab(context=context)
            await run_curtin_step(
                name="swap",
                stages=["swap"],
                step_config=self.generic_config(
                    swap_commands={
                        "subiquity": [
                            "curtin",
                            "swap",
                            "--fstab",
                            self.tpath("etc/fstab"),
                        ],
                    }
                ),
            )
            await fs_controller.finish_install(context=context)
            await self.setup_target(context=context)
        else:
            await run_curtin_step(
                name="partitioning",
                stages=["partitioning"],
                step_config=self.filesystem_config(
                    device_map_path=logs_dir / "device-map.json",
                ),
            )
            await run_curtin_step(
                name="extract",
                stages=["extract"],
                step_config=self.generic_config(),
                source=source,
            )
            if self.app.opts.dry_run:
                # In dry-run, extract does not do anything. Let's create what's
                # needed manually. Ideally, we would not hardcode
                # var/lib/dpkg/status because it is an implementation detail.
                status = "var/lib/dpkg/status"
                (root / status).parent.mkdir(parents=True, exist_ok=True)
                await arun_command(
                    [
                        "cp",
                        "-aT",
                        "--",
                        str(Path("/") / status),
                        str(root / status),
                    ]
                )
            await self.setup_target(context=context)

            # For OEM, we basically mimic what ubuntu-drivers does:
            # 1. Install each package with apt-get install
            # 2. For each package, run apt-get update using only the source
            # installed by said package.
            # 3. Run apt-get install again for each package. This will upgrade
            # them to the version found in the OEM archive.

            # NOTE In ubuntu-drivers, this is done in a single call to apt-get
            # install.
            for pkg in self.model.oem.metapkgs:
                await self.install_package(package=pkg.name)

            if self.model.network.has_network:
                for pkg in self.model.oem.metapkgs:
                    source_list = f"/etc/apt/sources.list.d/{pkg.name}.list"
                    await run_curtin_command(
                        self.app,
                        context,
                        "in-target",
                        "-t",
                        self.tpath(),
                        "--",
                        "apt-get",
                        "update",
                        "-o",
                        f"Dir::Etc::SourceList={source_list}",
                        "-o",
                        "Dir::Etc::SourceParts=/dev/null",
                        "--no-list-cleanup",
                        private_mounts=False,
                    )

                # NOTE In ubuntu-drivers, this is done in a single call to
                # apt-get install.
                for pkg in self.model.oem.metapkgs:
                    await self.install_package(package=pkg.name)

            # If we already have a kernel installed, don't bother requesting
            # curthooks to install it again or we might end up with two
            # kernels.
            if await list_installed_kernels(Path(self.tpath())):
                self.model.kernel.curthooks_no_install = True

            await run_curtin_step(
                name="curthooks",
                stages=["curthooks"],
                step_config=self.generic_config(),
            )
            # If the current source has a snapd_system_label here we should
            # really write recovery_system={snapd_system_label} to
            # {target}/var/lib/snapd/modeenv to get snapd to pick it up on
            # first boot. But not needed for now.
        rp = fs_controller.reset_partition
        if rp is not None:
            mounter = Mounter(self.app)
            async with mounter.mounted(rp.path) as mp:
                await run_curtin_step(
                    name="populate recovery",
                    stages=["extract"],
                    step_config=self.rp_config(logs_dir, mp.p()),
                    source="cp:///cdrom",
                )
            await self.create_rp_boot_entry(context=context, rp=rp)

    @with_context(description="creating boot entry for reset partition")
    async def create_rp_boot_entry(self, context, rp):
        fs_controller = self.app.controllers.Filesystem
        if not fs_controller.reset_partition_only:
            cp = await self.app.command_runner.run(
                ["lsblk", "-n", "-o", "UUID", rp.path], capture=True
            )
            uuid = cp.stdout.decode("ascii").strip()
            conf = grub_reset_conf.format(
                HEADER=generate_timestamped_header(), PARTITION=rp.number, UUID=uuid
            )
            with open(self.tpath("etc/grub.d/99_reset"), "w") as fp:
                os.chmod(fp.fileno(), 0o755)
                fp.write(conf)
            await run_curtin_command(
                self.app,
                context,
                "in-target",
                "-t",
                self.tpath(),
                "--",
                "update-grub",
                private_mounts=False,
            )
        if self.app.opts.dry_run and not is_uefi_bootable():
            # Can't even run efibootmgr in this case.
            return
        state = await self.app.package_installer.install_pkg("efibootmgr")
        if state != PackageInstallState.DONE:
            raise RuntimeError("could not install efibootmgr")
        efi_state_before = get_efibootmgr("/")
        cmd = [
            "efibootmgr",
            "--create",
            "--loader",
            "\\EFI\\boot\\shimx64.efi",
            "--disk",
            rp.device.path,
            "--part",
            str(rp.number),
            "--label",
            "Restore Ubuntu to factory state",
        ]
        await self.app.command_runner.run(cmd)
        efi_state_after = get_efibootmgr("/")
        new_bootnums = set(efi_state_after.entries) - set(efi_state_before.entries)
        if not new_bootnums:
            return
        new_bootnum = new_bootnums.pop()
        new_entry = efi_state_after.entries[new_bootnum]
        was_dup = False
        for entry in efi_state_before.entries.values():
            if entry.path == new_entry.path and entry.name == new_entry.name:
                was_dup = True
        if was_dup:
            cmd = [
                "efibootmgr",
                "--delete-bootnum",
                "--bootnum",
                new_bootnum,
            ]
        else:
            cmd = [
                "efibootmgr",
                "--bootorder",
                ",".join(efi_state_before.order),
            ]
        await self.app.command_runner.run(cmd)

    @with_context(description="creating fstab")
    async def create_core_boot_classic_fstab(self, *, context):
        with open(self.tpath("etc/fstab"), "w") as fp:
            fp.write("/run/mnt/ubuntu-boot/EFI/ubuntu /boot/grub none bind\n")

    @with_context()
    async def install(self, *, context):
        context.set("is-install-context", True)
        try:
            while True:
                self.app.update_state(ApplicationState.WAITING)

                await self.model.wait_install()

                if not self.app.interactive:
                    if "autoinstall" in self.app.kernel_cmdline:
                        await self.model.confirm()

                self.app.update_state(ApplicationState.NEEDS_CONFIRMATION)

                if await self.model.wait_confirmation():
                    break

            self.app.update_state(ApplicationState.RUNNING)

            if self.model.target is None:
                for_install_path = None
            elif self.supports_apt():
                for_install_path = "cp://" + await self.configure_apt(context=context)

                await self.app.hub.abroadcast(InstallerChannels.APT_CONFIGURED)
            else:
                fsc = self.app.controllers.Filesystem
                for_install_path = self.model.source.get_source(fsc._info.name)

            if self.app.controllers.Filesystem.reset_partition:
                self.app.package_installer.start_installing_pkg("efibootmgr")

            if self.model.target is not None:
                if os.path.exists(self.model.target):
                    await self.unmount_target(context=context, target=self.model.target)

            await self.curtin_install(context=context, source=for_install_path)

            self.app.update_state(ApplicationState.WAITING)

            await self.model.wait_postinstall()

            self.app.update_state(ApplicationState.RUNNING)

            await self.postinstall(context=context)

            self.app.update_state(ApplicationState.DONE)
        except Exception:
            kw = {}
            if self.tb_extractor.traceback:
                kw["Traceback"] = "\n".join(self.tb_extractor.traceback)
            self.app.make_apport_report(
                ErrorReportKind.INSTALL_FAIL, "install failed", **kw
            )
            raise

    @with_context(
        description="final system configuration", level="INFO", childlevel="DEBUG"
    )
    async def postinstall(self, *, context):
        autoinstall_path = os.path.join(
            self.app.root, "var/log/installer/autoinstall-user-data"
        )
        autoinstall_config = "#cloud-config\n" + yaml.dump(
            {"autoinstall": self.app.make_autoinstall()}
        )
        write_file(autoinstall_path, autoinstall_config)
        await self.configure_cloud_init(context=context)
        if self.supports_apt():
            packages = await self.get_target_packages(context=context)
            for package in packages:
                await self.install_package(context=context, package=package)
            if self.model.drivers.do_install:
                with context.child(
                    "ubuntu-drivers-install", "installing third-party drivers"
                ) as child:
                    udrivers = self.app.controllers.Drivers.ubuntu_drivers
                    await udrivers.install_drivers(root_dir=self.tpath(), context=child)
            if self.model.network.has_network:
                self.app.update_state(ApplicationState.UU_RUNNING)
                policy = self.model.updates.updates
                await self.run_unattended_upgrades(context=context, policy=policy)
            await self.restore_apt_config(context=context)
        if self.model.active_directory.do_join:
            hostname = self.model.identity.hostname
            if not hostname:
                with open(self.tpath("etc/hostname"), "r") as f:
                    hostname = f.read().strip()

            await self.app.controllers.Ad.join_domain(hostname, context)

    @with_context(description="configuring cloud-init")
    async def configure_cloud_init(self, context):
        await run_in_thread(self.model.configure_cloud_init)

    @with_context(description="calculating extra packages to install")
    async def get_target_packages(self, context):
        return await self.app.base_model.target_packages()

    @with_context(name="install_{package}", description="installing {package}")
    async def install_package(self, *, context, package):
        """Attempt to download the package up-to three times, then install it."""
        for attempt, attempts_remaining in enumerate(reversed(range(3))):
            try:
                with context.child("retrieving", f"retrieving {package}"):
                    await run_curtin_command(
                        self.app,
                        context,
                        "system-install",
                        "-t",
                        self.tpath(),
                        "--download-only",
                        "--",
                        package,
                        private_mounts=False,
                    )
            except subprocess.CalledProcessError:
                log.error(f"failed to download package {package}")
                if attempts_remaining > 0:
                    await asyncio.sleep(1 + attempt * 3)
                else:
                    raise
            else:
                break

        with context.child("unpacking", f"unpacking {package}"):
            await run_curtin_command(
                self.app,
                context,
                "system-install",
                "-t",
                self.tpath(),
                "--assume-downloaded",
                "--",
                package,
                private_mounts=False,
            )

    @with_context(description="restoring apt configuration")
    async def restore_apt_config(self, context):
        configurer = self.app.controllers.Mirror.final_apt_configurer
        await configurer.deconfigure(context, self.tpath())

    @with_context(description="downloading and installing {policy} updates")
    async def run_unattended_upgrades(self, context, policy):
        if self.app.opts.dry_run:
            aptdir = self.tpath("tmp")
        else:
            aptdir = self.tpath("etc/apt/apt.conf.d")
        os.makedirs(aptdir, exist_ok=True)
        apt_conf_contents = uu_apt_conf
        if policy == "all":
            apt_conf_contents += uu_apt_conf_update_all
        else:
            apt_conf_contents += uu_apt_conf_update_security
        fname = "zzzz-temp-installer-unattended-upgrade"
        with open(os.path.join(aptdir, fname), "wb") as apt_conf:
            apt_conf.write(apt_conf_contents)
            apt_conf.close()
            self.unattended_upgrades_ctx = context
            self.unattended_upgrades_cmd = await start_curtin_command(
                self.app,
                context,
                "in-target",
                "-t",
                self.tpath(),
                "--",
                "unattended-upgrades",
                "-v",
                private_mounts=True,
            )
            try:
                await self.unattended_upgrades_cmd.wait()
            except subprocess.CalledProcessError as cpe:
                log_process_streams(logging.ERROR, cpe, "Unattended upgrades")
                context.description = f"FAILED to apply {policy} updates"
            self.unattended_upgrades_cmd = None
            self.unattended_upgrades_ctx = None

    async def stop_unattended_upgrades(self):
        with self.unattended_upgrades_ctx.parent.child(
            "stop_unattended_upgrades", "cancelling update"
        ):
            await self.app.command_runner.run(
                [
                    "chroot",
                    self.tpath(),
                    "/usr/share/unattended-upgrades/unattended-upgrade-shutdown",
                    "--stop-only",
                ]
            )
            if self.app.opts.dry_run and self.unattended_upgrades_cmd is not None:
                self.unattended_upgrades_cmd.proc.terminate()


uu_apt_conf = b"""\
# Config for the unattended-upgrades run to avoid failing on battery power or
# a metered connection.
Unattended-Upgrade::OnlyOnACPower "false";
Unattended-Upgrade::Skip-Updates-On-Metered-Connections "true";
"""

uu_apt_conf_update_security = b"""\
# A copy of the current default unattended-upgrades config to grab
# security.
Unattended-Upgrade::Allowed-Origins {
        "${distro_id}:${distro_codename}";
        "${distro_id}:${distro_codename}-security";
        "${distro_id}ESMApps:${distro_codename}-apps-security";
        "${distro_id}ESM:${distro_codename}-infra-security";
};
"""

uu_apt_conf_update_all = b"""\
# A modified version of the unattended-upgrades default Allowed-Origins
# to include updates in the permitted origins.
Unattended-Upgrade::Allowed-Origins {
        "${distro_id}:${distro_codename}";
        "${distro_id}:${distro_codename}-updates";
        "${distro_id}:${distro_codename}-security";
        "${distro_id}ESMApps:${distro_codename}-apps-security";
        "${distro_id}ESM:${distro_codename}-infra-security";
};
"""

grub_reset_conf = """\
#!/bin/sh
{HEADER}

set -e

cat << EOF
menuentry "Restore Ubuntu to factory state" {
      search --no-floppy --hint '(hd0,{PARTITION})' --set --fs-uuid {UUID}
      linux  /casper/vmlinuz uuid={UUID} nopersistent
      initrd /casper/initrd
}
EOF
"""
