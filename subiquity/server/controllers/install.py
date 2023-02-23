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
import functools
import json
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Callable, Dict, List

import attr
import yaml

from subiquitycore.async_helpers import (
    run_bg_task,
    run_in_thread,
    )
from subiquitycore.context import with_context
from subiquitycore.file_util import write_file, generate_config_yaml

from subiquity.common.errorreport import ErrorReportKind
from subiquity.common.types import (
    ApplicationState,
    )
from subiquity.journald import (
    journald_listen,
    )
from subiquity.models.filesystem import ActionRenderMode
from subiquity.server.controller import (
    SubiquityController,
    )
from subiquity.server.curtin import (
    run_curtin_command,
    start_curtin_command,
    )
from subiquity.server.types import (
    InstallerChannels,
    )


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


@attr.s(auto_attribs=True)
class CurtinInstallStep:
    """Represents the parameters of a single invocation of curtin install."""
    controller: "InstallController"
    name: str
    stages: List[str]
    config_file: Path
    log_file: Path
    error_file: Path
    resume_data_file: Path
    source: str
    acquire_config: Callable[["CurtinInstallStep"], Dict[str, Any]]

    @with_context(
        description="executing curtin install {self.name} step")
    async def run(self, context):
        """ Run a curtin install step. """

        self.controller.app.note_file_for_apport(
                f"Curtin{self.name}Config", str(self.config_file))

        self.controller.write_config(
                config_file=self.config_file,
                config=self.acquire_config(self)
                )

        # Make sure the log directory exists.
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Add a marker to identify the step in the log file.
        with open(str(self.log_file), mode="a") as fh:
            fh.write(f"\n---- [[ subiquity step {self.name} ]] ----\n")

        await run_curtin_command(
            self.controller.app, context, "install", self.source,
            "--set", f'json:stages={json.dumps(self.stages)}',
            config=str(self.config_file), private_mounts=False)


@attr.s(auto_attribs=True)
class CurtinPartitioningStep(CurtinInstallStep):
    device_map_path: Path

    async def run(self, context):
        await super().run(context=context)
        with open(self.device_map_path) as fp:
            device_map = json.load(fp)
        fs = self.controller.app.controllers.Filesystem
        fs.update_devices(device_map)


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
        self.tb_extractor.feed(event['MESSAGE'])

    def write_config(self, config_file: Path, config: Any) -> None:
        """ Create a YAML file that represents the curtin install configuration
        specified.  """
        config_file.parent.mkdir(parents=True, exist_ok=True)
        generate_config_yaml(str(config_file), config)

    def acquire_generic_config(self,
                               step: CurtinInstallStep,
                               **kw) -> Dict[str, Any]:
        """ Return a dictionary object to be used as the configuration of a
        generic curtin install step. """
        config = self.model.render()
        config["install"]["log_file"] = str(step.log_file)
        config["install"]["log_file_append"] = True
        config["install"]["error_tarfile"] = str(step.error_file)
        config["install"]["resume_data"] = str(step.resume_data_file)
        config.update(kw)
        return config

    def acquire_initial_config(self,
                               step: CurtinInstallStep) -> Dict[str, Any]:
        """ Return a dictionary object to be used as the configuration of the
        initial curtin install step. """
        return {
            "install": {
                "target": self.model.target,
                "unmount": "disabled",
                "save_install_config": False,
                "save_install_log": False,
                "log_file": str(step.log_file),
                "log_file_append": True,
                "error_tarfile": str(step.error_file),
                "resume_data": str(step.resume_data_file),
            }
        }

    def acquire_filesystem_config(
            self, step: CurtinPartitioningStep,
            mode: ActionRenderMode = ActionRenderMode.DEFAULT
            ) -> Dict[str, Any]:
        cfg = self.acquire_initial_config(step)
        cfg.update(self.model.filesystem.render(mode=mode))
        cfg['storage']['device_map_path'] = str(step.device_map_path)
        return cfg

    @with_context(description="umounting /target dir")
    async def unmount_target(self, *, context, target):
        await run_curtin_command(self.app, context, 'unmount', '-t', target,
                                 private_mounts=False)
        if not self.app.opts.dry_run:
            shutil.rmtree(target)

    @with_context(
        description="configuring apt", level="INFO", childlevel="DEBUG")
    async def configure_apt(self, *, context):
        mirror = self.app.controllers.Mirror
        configurer = await mirror.wait_config()
        return await configurer.configure_for_install(context)

    async def setup_target(self, context):
        mirror = self.app.controllers.Mirror
        await mirror.apt_configurer.setup_target(context, self.tpath())

    @with_context(
        description="installing system", level="INFO", childlevel="DEBUG")
    async def curtin_install(self, *, context, source):
        logs_dir_prefix = Path(
                self.app.opts.output_base if self.app.opts.dry_run else "/")

        logs_dir = logs_dir_prefix / "var/log/installer"
        logs_dir.mkdir(parents=True, exist_ok=True)

        config_dir = logs_dir / "curtin-install"

        install_log_file = logs_dir / "curtin-install.log"
        error_file = logs_dir / "curtin-errors.tar"

        self.app.note_file_for_apport("CurtinErrors", str(error_file))
        self.app.note_file_for_apport("CurtinLog", str(install_log_file))

        resume_data_file = Path(tempfile.mkdtemp()) / "resume-data.json"

        def make_curtin_step(name, stages, acquire_config, *,
                             cls=CurtinInstallStep, **kw):
            return cls(
                controller=self,
                name=name,
                stages=stages,
                config_file=config_dir / f"subiquity-{name}.conf",
                log_file=install_log_file,
                error_file=error_file,
                resume_data_file=resume_data_file,
                source=source,
                acquire_config=acquire_config,
                **kw,
            )

        steps = [
            make_curtin_step(
                "initial",
                stages=[],
                acquire_config=self.acquire_initial_config
            ).run,
            ]
        fs_controller = self.app.controllers.Filesystem
        if fs_controller.is_core_boot_classic():
            steps.append(
                make_curtin_step(
                    name="partitioning", stages=["partitioning"],
                    acquire_config=functools.partial(
                        self.acquire_filesystem_config,
                        mode=ActionRenderMode.DEVICES),
                    cls=CurtinPartitioningStep,
                    device_map_path=logs_dir / "device-map-partition.json",
                    ).run,
                )
            if fs_controller.use_tpm:
                steps.append(fs_controller.setup_encryption)
            steps.extend([
                make_curtin_step(
                    name="formatting", stages=["partitioning"],
                    acquire_config=functools.partial(
                        self.acquire_filesystem_config,
                        mode=ActionRenderMode.FORMAT_MOUNT),
                    cls=CurtinPartitioningStep,
                    device_map_path=logs_dir / "device-map-format.json",
                    ).run,
                make_curtin_step(
                    name="extract", stages=["extract"],
                    acquire_config=self.acquire_generic_config,
                    ).run,
                self.create_core_boot_classic_fstab,
                make_curtin_step(
                        name="swap", stages=["swap"],
                        acquire_config=functools.partial(
                            self.acquire_generic_config,
                            swap_commands={
                                'subiquity': [
                                    'curtin', 'swap',
                                    '--fstab', self.tpath('etc/fstab'),
                                    ],
                                }),
                    ).run,
                fs_controller.finish_install,
                self.setup_target,
                ])
        else:
            steps.extend([
                make_curtin_step(
                    name="partitioning", stages=["partitioning"],
                    acquire_config=self.acquire_filesystem_config,
                    cls=CurtinPartitioningStep,
                    device_map_path=logs_dir / "device-map.json",
                    ).run,
                make_curtin_step(
                    name="extract", stages=["extract"],
                    acquire_config=self.acquire_generic_config,
                    ).run,
                self.setup_target,
                make_curtin_step(
                        name="curthooks", stages=["curthooks"],
                        acquire_config=self.acquire_generic_config,
                    ).run,
                ])
            # If the current source has a snapd_system_label here we should
            # really write recovery_system={snapd_system_label} to
            # {target}/var/lib/snapd/modeenv to get snapd to pick it up on
            # first boot. But not needed for now.

        for step in steps:
            await step(context=context)

    @with_context(description="creating fstab")
    async def create_core_boot_classic_fstab(self, *, context):
        with open(self.tpath('etc/fstab'), 'w') as fp:
            fp.write("/run/mnt/ubuntu-boot/EFI/ubuntu /boot/grub none bind\n")

    @with_context()
    async def install(self, *, context):
        context.set('is-install-context', True)
        try:
            while True:
                self.app.update_state(ApplicationState.WAITING)

                await self.model.wait_install()

                if not self.app.interactive:
                    if 'autoinstall' in self.app.kernel_cmdline:
                        self.model.confirm()

                self.app.update_state(ApplicationState.NEEDS_CONFIRMATION)

                if await self.model.wait_confirmation():
                    break

            self.app.update_state(ApplicationState.RUNNING)

            for_install_path = await self.configure_apt(context=context)

            await self.app.hub.abroadcast(InstallerChannels.APT_CONFIGURED)

            if os.path.exists(self.model.target):
                await self.unmount_target(
                    context=context, target=self.model.target)

            await self.curtin_install(
                context=context, source='cp://' + for_install_path)

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
                ErrorReportKind.INSTALL_FAIL, "install failed", **kw)
            raise

    @with_context(
        description="final system configuration", level="INFO",
        childlevel="DEBUG")
    async def postinstall(self, *, context):
        autoinstall_path = os.path.join(
            self.app.root, 'var/log/installer/autoinstall-user-data')
        autoinstall_config = "#cloud-config\n" + yaml.dump(
            {"autoinstall": self.app.make_autoinstall()})
        write_file(autoinstall_path, autoinstall_config)
        await self.configure_cloud_init(context=context)
        packages = await self.get_target_packages(context=context)
        for package in packages:
            await self.install_package(context=context, package=package)
        if self.model.drivers.do_install:
            with context.child(
                    "ubuntu-drivers-install",
                    "installing third-party drivers") as child:
                ubuntu_drivers = self.app.controllers.Drivers.ubuntu_drivers
                await ubuntu_drivers.install_drivers(root_dir=self.tpath(),
                                                     context=child)

        if self.model.network.has_network:
            self.app.update_state(ApplicationState.UU_RUNNING)
            policy = self.model.updates.updates
            await self.run_unattended_upgrades(context=context, policy=policy)
        await self.restore_apt_config(context=context)
        if self.model.ad.do_join:
            hostname = self.model.identity.hostname
            if not hostname:
                with open(self.tpath('etc/hostname'), 'r') as f:
                    hostname = f.read().strip()

            await self.app.controllers.AD.join_domain(hostname, context)

    @with_context(description="configuring cloud-init")
    async def configure_cloud_init(self, context):
        await run_in_thread(self.model.configure_cloud_init)

    @with_context(description="calculating extra packages to install")
    async def get_target_packages(self, context):
        return await self.app.base_model.target_packages()

    @with_context(
        name="install_{package}",
        description="installing {package}")
    async def install_package(self, *, context, package):
        with context.child('retrieving', f'retrieving {package}'):
            await run_curtin_command(
                self.app, context, 'system-install', '-t', self.tpath(),
                '--download-only',
                '--', package,
                private_mounts=False)
        with context.child('unpacking', f'unpacking {package}'):
            await run_curtin_command(
                self.app, context, 'system-install', '-t', self.tpath(),
                '--assume-downloaded',
                '--', package,
                private_mounts=False)

    @with_context(description="restoring apt configuration")
    async def restore_apt_config(self, context):
        configurer = self.app.controllers.Mirror.apt_configurer
        await configurer.deconfigure(context, self.tpath())

    @with_context(description="downloading and installing {policy} updates")
    async def run_unattended_upgrades(self, context, policy):
        if self.app.opts.dry_run:
            aptdir = self.tpath("tmp")
        else:
            aptdir = self.tpath("etc/apt/apt.conf.d")
        os.makedirs(aptdir, exist_ok=True)
        apt_conf_contents = uu_apt_conf
        if policy == 'all':
            apt_conf_contents += uu_apt_conf_update_all
        else:
            apt_conf_contents += uu_apt_conf_update_security
        fname = 'zzzz-temp-installer-unattended-upgrade'
        with open(os.path.join(aptdir, fname), 'wb') as apt_conf:
            apt_conf.write(apt_conf_contents)
            apt_conf.close()
            self.unattended_upgrades_ctx = context
            self.unattended_upgrades_cmd = await start_curtin_command(
                self.app, context, "in-target", "-t", self.tpath(),
                "--", "unattended-upgrades", "-v",
                private_mounts=True)
            await self.unattended_upgrades_cmd.wait()
            self.unattended_upgrades_cmd = None
            self.unattended_upgrades_ctx = None

    async def stop_unattended_upgrades(self):
        with self.unattended_upgrades_ctx.parent.child(
                "stop_unattended_upgrades",
                "cancelling update"):
            await self.app.command_runner.run([
                'chroot', self.tpath(),
                '/usr/share/unattended-upgrades/'
                'unattended-upgrade-shutdown',
                '--stop-only',
                ])
            if self.app.opts.dry_run and \
               self.unattended_upgrades_cmd is not None:
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
