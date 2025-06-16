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
import glob
import json
import logging
import os
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from curtin.config import merge_config
from curtin.distro import list_kernels

from subiquity.common.errorreport import ErrorReportKind
from subiquity.common.pkg import TargetPkg
from subiquity.common.types import ApplicationState, PackageInstallState
from subiquity.journald import journald_listen
from subiquity.models.filesystem import ActionRenderMode, Partition
from subiquity.server.controller import SubiquityController
from subiquity.server.controllers.filesystem import VariationInfo
from subiquity.server.curtin import run_curtin_command
from subiquity.server.mounter import Mounter, Mountpoint
from subiquity.server.types import InstallerChannels
from subiquitycore.async_helpers import run_in_thread
from subiquitycore.context import with_context
from subiquitycore.file_util import (
    generate_config_yaml,
    generate_timestamped_header,
    write_file,
)
from subiquitycore.utils import arun_command, log_process_streams

log = logging.getLogger("subiquity.server.controllers.install")


class CurtinInstallError(Exception):
    def __init__(self, *, stages: List[str]) -> None:
        super().__init__()
        self.stages = stages


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
        self.bridge_kernel_decided = asyncio.Event()
        self.app.hub.subscribe(
            InstallerChannels.BRIDGE_KERNEL_DECIDED, self.bridge_kernel_decided.set
        )

        self.tb_extractor = TracebackExtractor()

    def interactive(self):
        return True

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
        if "storage" in cfg and device_map_path is not None:
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

    def write_autoinstall_config(self) -> None:
        autoinstall_path = os.path.join(
            self.app.root, "var/log/installer/autoinstall-user-data"
        )
        autoinstall_config = (
            "#cloud-config\n"
            "# See the autoinstall documentation at:\n"
            "# https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html\n"  # noqa: E501
            + yaml.dump({"autoinstall": self.app.make_autoinstall()})
        )
        # As autoinstall-user-data contains a password hash, we want this file
        # to have a very restrictive mode and ownership.
        write_file(autoinstall_path, autoinstall_config, mode=0o400, group="root")

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
        keyboard = self.app.controllers.Keyboard
        await keyboard.setup_target(context=context)

    @staticmethod
    def error_in_curtin_invocation(exc: Exception) -> Optional[str]:
        """If the exception passed as an argument corresponds to an error
        during the invocation of a single curtin stage, return the name of the
        stage. Otherwise, return None."""
        if not isinstance(exc, CurtinInstallError):
            return None
        if len(exc.stages) != 1:
            return None
        return exc.stages[0]

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

        try:
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
        except subprocess.CalledProcessError:
            raise CurtinInstallError(stages=stages)

        device_map_path = config.get("storage", {}).get("device_map_path")
        if device_map_path is not None:
            with open(device_map_path) as fp:
                device_map = json.load(fp)
            self.app.controllers.Filesystem.update_devices(device_map)

    async def pre_curthooks_oem_configuration(self, context):
        async def install_oem_metapackages(ctx):
            # For OEM, we basically mimic what ubuntu-drivers does:
            # 1. Install each package with apt-get install
            # 2. For each package, run apt-get update using only the source
            # installed by said package.
            # 3. Run apt-get install again for each package. This will upgrade
            # them to the version found in the OEM archive.

            # NOTE In ubuntu-drivers, this is done in a single call to apt-get
            # install.
            for pkg in self.model.oem.metapkgs:
                await self.install_package(package=pkg.name, context=ctx)

            if not self.model.network.has_network:
                return

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

        if not self.model.oem.metapkgs:
            return

        # cause existing kernels to be removed, if needed.  If a kernel is
        # already in the minimal layer, it might not be the intended one, so
        # tell kernel to remove that pre-installed kernel.  This augments the
        # curtin ensure_one_kernel logic as by the time it knows what to do,
        # there are already two kernels, so instead we calculate the "before"
        # set of kernels now.  Note that in the case where the one preinstalled
        # kernel is also the one that the OEM logic tells us to install, that
        # kernel stays installed despite being on the remove list we supply
        # here, since the curthook act of installing a kernel doesn't change
        # state.
        target = self.tpath()
        if self.app.opts.dry_run:
            existing_kernels = []
        else:
            existing_kernels = list_kernels(target=target)

        self.app.base_model.kernel.curthooks_install = False
        self.app.base_model.kernel.remove = existing_kernels

        with context.child(
            "install_oem_metapackages", "installing applicable OEM metapackages"
        ) as child:
            await install_oem_metapackages(child)

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
        elif fs_controller.use_snapd_install_api():
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
            if source is not None:
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
            await self.setup_target(context=context)
        else:
            await run_curtin_step(
                name="partitioning",
                stages=["partitioning"],
                step_config=self.filesystem_config(
                    device_map_path=logs_dir / "device-map.json",
                ),
                source=source,
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

            if self.supports_apt():
                await self.pre_curthooks_oem_configuration(context=context)

            await self.bridge_kernel_decided.wait()

            await run_curtin_step(
                name="curthooks",
                stages=["curthooks"],
                step_config=self.generic_config(),
            )
            # If the current source has a snapd_system_label here we should
            # really write recovery_system={snapd_system_label} to
            # {target}/var/lib/snapd/modeenv to get snapd to pick it up on
            # first boot. But not needed for now.
        rp = fs_controller.model.reset_partition
        if rp is not None:
            mounter = Mounter(self.app)
            rp_target = os.path.join(self.app.root, "factory-reset")
            mp = await mounter.mount(rp.path, mountpoint=rp_target)
            await run_curtin_step(
                name="populate recovery",
                stages=["extract"],
                step_config=self.rp_config(logs_dir, mp.p()),
                source="cp:///cdrom",
            )
            new_casper_uuid = await self.adjust_rp(rp, mp)
            await self.configure_rp_boot(
                context=context, rp=rp, casper_uuid=new_casper_uuid
            )
        else:
            await self.maybe_configure_existing_rp_boot(context=context)

    async def adjust_rp(self, rp: Partition, mp: Mountpoint) -> str:
        if self.app.opts.dry_run:
            return
        # Once the installer has been copied to the RP, we need to make two
        # adjustments:
        #
        # 1. set a new "casper uuid" so that booting from the install
        #    media again, or booting from the RP but with the install
        #    media still attached, does not get confused about which
        #    device to use as /cdrom.
        #
        # 2. add "rp-partuuid" to the kernel command line in grub.cfg
        #    so that subiquity can identify when it is running from
        #    the recovery partition and add a reference to it to
        #    grub.cfg on the target system in that case.
        grub_cfg_path = mp.p("boot/grub/grub.cfg")
        new_cfg = []
        new_casper_uuid = str(uuid.uuid4())
        cp = await self.app.command_runner.run(
            ["lsblk", "-n", "-o", "PARTUUID", rp.path], capture=True
        )
        rp_uuid = cp.stdout.decode("ascii").strip()
        with open(grub_cfg_path) as fp:
            for line in fp:
                words = shlex.split(line)
                if words and words[0] == "linux" and "---" in words:
                    index = words.index("---")
                    words = [
                        word
                        for word in words
                        if not (
                            word.startswith("uuid=") or word.startswith("rp-partuuid=")
                        )
                    ]
                    words[index - 1 : index - 1] = [
                        "uuid=" + new_casper_uuid,
                        "rp-partuuid=" + rp_uuid,
                    ]
                    new_cfg.append(shlex.join(words) + "\n")
                else:
                    new_cfg.append(line)
        with open(grub_cfg_path, "w") as fp:
            fp.write("".join(new_cfg))
        for casper_uuid_file in glob.glob(mp.p(".disk/casper-uuid-*")):
            with open(casper_uuid_file, "w") as fp:
                fp.write(new_casper_uuid + "\n")
        return new_casper_uuid

    @with_context(description="configuring grub menu entry for factory reset")
    async def configure_rp_boot_grub(self, context, rp: Partition):
        # Add a grub menu entry to boot from the RP
        cp = await self.app.command_runner.run(
            ["lsblk", "-n", "-o", "UUID", rp.path], capture=True
        )
        fs_uuid = cp.stdout.decode("ascii").strip()
        conf = grub_reset_conf.format(
            HEADER=generate_timestamped_header(),
            PARTITION=rp.number,
            FS_UUID=fs_uuid,
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

    async def configure_rp_boot(self, context, rp: Partition, casper_uuid: str):
        if self.model.target is not None and not self.opts.dry_run:
            await self.configure_rp_boot_grub(context=context, rp=rp)

    async def maybe_configure_existing_rp_boot(self, context):
        # We are not creating a reset partition here if we are running
        # from one we still want to configure booting from it.

        # Look for the command line argument added in adjust_rp)
        # above.
        rp_partuuid = self.app.kernel_cmdline.get("rp-partuuid")
        if rp_partuuid is None:
            # Most likely case: we are not running from an reset partition
            return
        rp = self.app.base_model.filesystem.partition_by_partuuid(rp_partuuid)
        if rp is None:
            # This shouldn't happen, but don't crash.
            return
        casper_uuid = None
        for casper_uuid_file in glob.glob("/cdrom/.disk/casper-uuid-*"):
            with open(casper_uuid_file) as fp:
                casper_uuid = fp.read().strip()
        if casper_uuid is None:
            # This also shouldn't happen, but, again, don't crash.
            return
        await self.configure_rp_boot(context=context, rp=rp, casper_uuid=casper_uuid)

    @with_context(description="creating fstab")
    async def create_core_boot_classic_fstab(self, *, context):
        with open(self.tpath("etc/fstab"), "w") as fp:
            fp.write("/run/mnt/ubuntu-boot/EFI/ubuntu /boot/grub none bind\n")

    async def install_live_packages(self, *, context):
        before, during = await self.model.live_packages()
        if len(before) < 1 and len(during) < 1:
            return

        with context.child("live-packages", "installing packages to live system"):
            for package in before:
                state = await self.app.package_installer.install_pkg(package)
                if state != PackageInstallState.DONE:
                    raise RuntimeError(f"could not install {package}")
            for package in during:
                self.app.package_installer.start_installing_pkg(package)

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

            await self.install_live_packages(context=context)

            if self.model.target is not None:
                if os.path.exists(self.model.target):
                    await self.unmount_target(context=context, target=self.model.target)

            await self.curtin_install(context=context, source=for_install_path)

            self.app.update_state(ApplicationState.WAITING)

            await self.model.wait_postinstall()

            self.app.update_state(ApplicationState.RUNNING)

            await self.postinstall(context=context)

            self.app.update_state(ApplicationState.LATE_COMMANDS)
            await self.app.controllers.Late.run()

            self.app.update_state(ApplicationState.DONE)
        except Exception as exc:
            kw = {}
            if self.tb_extractor.traceback:
                kw["Traceback"] = "\n".join(self.tb_extractor.traceback)
            text = self.error_in_curtin_invocation(exc) or "install failed"

            self.app.make_apport_report(ErrorReportKind.INSTALL_FAIL, text, **kw)
            raise

    async def platform_postinstall(self):
        """Run architecture specific commands/quirks"""
        if platform.machine() == "s390x":
            try:
                # Ensure we boot from the installed system.
                await arun_command(["chreipl", "/target/boot"])
            except subprocess.CalledProcessError as cpe:
                if cpe.stderr is not None:
                    log.warning("chreipl stderr:\n%s", cpe.stderr)
                raise

    def kernel_components(self) -> List[str]:
        if not self.supports_apt():
            return []
        if not self.model.drivers.do_install:
            return []
        info: VariationInfo = self.app.controllers.Filesystem._info
        kernel_components = info.available_kernel_components
        nvidia_driver_offered: bool = False
        # so here we make the jump from the `ubuntu-drivers` recommendation and
        # map that, as close as we can, to kernel components.  Currently just
        # handling nvidia.  Note that it's highly likely that the version
        # offered in archive will be newer than what is offered by pc-kernel
        # (570 in plucky archive vs 550 in noble pc-kernel at time of writing).
        # for first pass, accept the matching version, if that's an option

        # Components have the naming convention nvidia-$ver-{erd,uda}-{user,ko}
        # erd are the Server drivers, uda are Desktop drivers.  Support the
        # desktop ones for now.
        for driver in sorted(self.app.controllers.Drivers.drivers, reverse=True):
            m = re.fullmatch("nvidia-driver-([0-9]+)", driver)
            if not m:
                continue
            nvidia_driver_offered = True
            v = m.group(1)
            ko = f"nvidia-{v}-uda-ko"
            user = f"nvidia-{v}-uda-user"
            if ko in kernel_components and user in kernel_components:
                return [ko, user]
        # if we don't match there, accept the newest reasonable version
        if nvidia_driver_offered:
            for component in sorted(kernel_components, reverse=True):
                m = re.fullmatch("nvidia-([0-9]+)-uda-ko", component)
                if not m:
                    continue
                ko = component
                v = m.group(1)
                user = f"nvidia-{v}-uda-user"
                if user in kernel_components:
                    return [ko, user]
        return []

    @with_context(
        description="final system configuration", level="INFO", childlevel="DEBUG"
    )
    async def postinstall(self, *, context):
        self.write_autoinstall_config()
        try:
            if self.supports_apt():
                packages = await self.get_target_packages(context=context)
                for package in packages:
                    if package.skip_when_offline and not self.model.network.has_network:
                        log.warning(
                            "skipping installation of package %s when"
                            " performing an offline install.",
                            package.name,
                        )
                        continue
                    await self.install_package(context=context, package=package.name)
        finally:
            await self.configure_cloud_init(context=context)

        fs_controller = self.app.controllers.Filesystem
        if fs_controller.use_snapd_install_api():
            if fs_controller.use_tpm:
                # This will generate a recovery key which will initially expire
                # after a very short duration (e.g., 5 minutes).
                # We need to reach the finish_install step within that timeframe,
                # otherwise the key will be considered expired. So let's keep
                # the two calls next to one another.
                await fs_controller.fetch_core_boot_recovery_key()
            await fs_controller.finish_install(
                context=context, kernel_components=self.kernel_components()
            )

        if self.supports_apt():
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
        await self.platform_postinstall()
        self.model.filesystem.copy_artifacts_to_target()

    @with_context(description="configuring cloud-init")
    async def configure_cloud_init(self, context):
        await run_in_thread(self.model.configure_cloud_init)

    @with_context(description="calculating extra packages to install")
    async def get_target_packages(self, context) -> List[TargetPkg]:
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
        apt_conf_path = Path(aptdir) / "zzzz-temp-installer-unattended-upgrade"
        apt_conf_path.write_bytes(apt_conf_contents)
        try:
            await run_curtin_command(
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
        except subprocess.CalledProcessError as cpe:
            log_process_streams(logging.ERROR, cpe, "Unattended upgrades")
            context.description = f"FAILED to apply {policy} updates"
        finally:
            apt_conf_path.unlink()


uu_apt_conf = b"""\
# Config for the unattended-upgrades run to avoid failing on battery power or
# a metered connection.
Unattended-Upgrade::OnlyOnACPower "false";
Unattended-Upgrade::Skip-Updates-On-Metered-Connections "true";

# Set MinimalSteps to false to speedup install times. "true", the default, will
# atmoize updates to enable interrupts between downloads, but this causes the
# install to slow down considerably. This is a major bottleneck of the install.
# Some testing shows a 3-4x speedup on the unattended-upgrades section of the
# install when this is set to false. However, this will make interrupting
# this section of the install process difficult.
Unattended-Upgrade::MinimalSteps "false";
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
menuentry "Restore Ubuntu to factory state" {{
      search --no-floppy --hint '(hd0,{PARTITION})' --set --fs-uuid {FS_UUID}
      chainloader /EFI/boot/bootx64.efi
}}
EOF
"""
