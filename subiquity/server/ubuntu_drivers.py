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

"""Module that defines helpers to use the ubuntu-drivers command."""

import logging
import os
import re
import subprocess
from abc import ABC, abstractmethod
from typing import List, Type

import yaml

from subiquity.server.curtin import run_curtin_command
from subiquitycore.file_util import copy_file_if_exists, write_file
from subiquitycore.utils import arun_command, system_scripts_env

log = logging.getLogger("subiquity.server.ubuntu_drivers")


class CommandNotFoundError(Exception):
    """Exception to be raised when the ubuntu-drivers command is not
    available.
    """


class UbuntuDriversInterface(ABC):
    def __init__(self, app, gpgpu: bool) -> None:
        self.app = app

        self.list_oem_cmd = [
            "ubuntu-drivers",
            "list-oem",
        ]
        self.list_drivers_cmd = [
            "ubuntu-drivers",
            "list",
            "--recommended",
        ]
        # Because of LP #1966413, the following command will also install
        # relevant OEM meta-packages on affected ubuntu-drivers-common
        # versions (unless --gpgpu is also passed).
        # This is not ideal but should be acceptable because we want OEM
        # meta-packages installed unconditionally (except in autoinstall).
        self.install_drivers_cmd = [
            "env",
            "DEBIAN_FRONTEND=noninteractive",
            "ubuntu-drivers",
            "install",
            "--no-oem",
        ]
        if gpgpu:
            self.list_drivers_cmd.append("--gpgpu")
            self.install_drivers_cmd.append("--gpgpu")

    @abstractmethod
    async def ensure_cmd_exists(self, root_dir: str) -> None:
        pass

    @abstractmethod
    async def list_drivers(self, root_dir: str, context) -> List[str]:
        pass

    @abstractmethod
    async def list_oem(self, root_dir: str, context) -> List[str]:
        pass

    async def install_drivers(self, root_dir: str, context) -> None:
        await run_curtin_command(
            self.app,
            context,
            "in-target",
            "-t",
            root_dir,
            "--",
            *self.install_drivers_cmd,
            private_mounts=True,
        )

    def _drivers_from_output(self, output: str) -> List[str]:
        """Parse the output of ubuntu-drivers list --recommended and return a
        list of drivers."""
        drivers: List[str] = []
        # Drivers are listed one per line, but some drivers are followed by a
        # linux-modules-* package (which we are not interested in showing).
        # e.g.,:
        # $ ubuntu-drivers list --recommended
        # nvidia-driver-470 linux-modules-nvidia-470-generic-hwe-20.04
        for line in [x.strip() for x in output.split("\n")]:
            if not line:
                continue
            package = line.split(" ", maxsplit=1)[0]
            if package.startswith("oem-") and package.endswith("-meta"):
                # Ignore oem-*-meta packages (this would not be needed if we
                # had passed --no-oem but ..)
                continue
            drivers.append(package)

        return drivers

    def _oem_metapackages_from_output(self, output: str) -> List[str]:
        """Parse the output of ubuntu-drivers list-oem and return a list of
        packages."""
        metapackages: List[str] = []
        # Packages are listed one per line.
        for line in [x.strip() for x in output.split("\n")]:
            if not line:
                continue
            metapackages.append(line)

        return metapackages


class UbuntuDriversClientInterface(UbuntuDriversInterface):
    """UbuntuDrivers interface that uses the ubuntu-drivers command from the
    specified root directory."""

    async def ensure_cmd_exists(self, root_dir: str) -> None:
        # TODO This does not tell us if the "--recommended" option is
        # available.
        try:
            await self.app.command_runner.run(
                ["chroot", root_dir, "sh", "-c", "command -v ubuntu-drivers"]
            )
        except subprocess.CalledProcessError:
            raise CommandNotFoundError(
                f"Command ubuntu-drivers is not available in {root_dir}"
            )

    async def list_drivers(self, root_dir: str, context) -> List[str]:
        result = await run_curtin_command(
            self.app,
            context,
            "in-target",
            "-t",
            root_dir,
            "--",
            *self.list_drivers_cmd,
            capture=True,
            private_mounts=True,
        )
        # Currently we have no way to specify universal_newlines=True or
        # encoding="utf-8" to run_curtin_command so we need to decode the
        # output.
        return self._drivers_from_output(result.stdout.decode("utf-8"))

    async def list_oem(self, root_dir: str, context) -> List[str]:
        result = await run_curtin_command(
            self.app,
            context,
            "in-target",
            "-t",
            root_dir,
            "--",
            *self.list_oem_cmd,
            capture=True,
            private_mounts=True,
        )
        # Currently we have no way to specify universal_newlines=True or
        # encoding="utf-8" to run_curtin_command so we need to decode the
        # output.
        return self._oem_metapackages_from_output(result.stdout.decode("utf-8"))


class UbuntuDriversFakePCIDevicesInterface(UbuntuDriversInterface):
    """An implementation of ubuntu-drivers that wraps the calls with
    the umockdev wrapper script.


    Requires an online install to download umockdev packages or
    a modified ISOs with the packages added to the pool.
    """

    def __init__(self, app, gpgpu: bool) -> None:
        super().__init__(app, gpgpu)

        # PCI devices can be passed on the kernel command line as a comma
        # separated list:
        #  subiquity-fake-pci-devices=pci:v00001234d00001234,pci:v00005678d00005678
        pcis = app.opts.kernel_cmdline.get("subiquity-fake-pci-devices")
        devs = [self.modalias_to_config(d) for d in pcis.split(",") if d != ""]
        self.dev_config = {"devices": devs}
        log.debug(f"writing umockdev_config: {self.dev_config}")

        # write config to live environment
        self.dev_config_path = "/tmp/umockdev_config.yaml"
        write_file(self.dev_config_path, yaml.safe_dump(self.dev_config), mode=0o777)

        prefix: list[str] = [
            "subiquity-umockdev-wrapper",  # vendored in system_scripts
            "--config",
            self.dev_config_path,
            "--",  # Don't let wrapper consume ubuntu-drivers feature flags
        ]

        self.sys_env = system_scripts_env()

        self.pre_req_cmd = [
            "apt-get",
            "install",
            "-oDPkg::Lock::Timeout=-1",  # avoid oem vs drivers lock timeout
            "-y",
            "umockdev",
            "gir1.2-umockdev-1.0",
        ]

        self.list_drivers_cmd = prefix + self.list_drivers_cmd
        self.list_oem_cmd = prefix + self.list_oem_cmd
        self.install_drivers_cmd = prefix + self.install_drivers_cmd

    def modalias_to_config(self, modalias: str) -> dict[str, list[dict[str, str]]]:
        """Generate a device config for umockdev-wrapper given a modalias."""
        matches = re.compile(
            r"pci:v(?P<vendor_id>[0-9A-F]{8})d(?P<device_id>[0-9A-F]{8})"
        ).match(modalias)

        assert matches is not None, f"{modalias} is malformed."

        return {
            "modalias": modalias,
            "vendor": f"0x{matches.group('vendor_id')}",
            "device": f"0x{matches.group('device_id')}",
        }

    async def ensure_cmd_exists(self, root_dir: str) -> None:
        # TODO This does not tell us if the "--recommended" option is
        # available.
        try:
            await arun_command(["sh", "-c", "command -v ubuntu-drivers"], check=True)
        except subprocess.CalledProcessError:
            raise CommandNotFoundError(
                f"Command ubuntu-drivers is not available in {root_dir}"
            )
        # Install wrapper script prerequisites on live system
        try:
            await arun_command(self.pre_req_cmd, check=True)
        except subprocess.CalledProcessError as err:
            log.debug(f"ensure_cmd returned with exit code {err.returncode}")
            log.debug(f"ensure_cmd stdout: {err.stdout}")
            log.debug(f"ensure_cmd stderr: {err.stderr}")
            raise Exception("Installing umockdev failed. Quitting early.")

    async def list_drivers(self, root_dir: str, context) -> List[str]:
        result = await arun_command(self.list_drivers_cmd, env=self.sys_env)
        return self._drivers_from_output(result.stdout)

    async def list_oem(self, root_dir: str, context) -> List[str]:
        result = await arun_command(self.list_oem_cmd, env=self.sys_env)
        return self._oem_metapackages_from_output(result.stdout)

    def _get_wrapper_path(self) -> str | None:
        # Find subiquity-umockdev-wrapper on live system
        base_paths: list[str] = self.sys_env["PATH"].split(":")
        script_path: str | None = None

        log.debug(f"Looking in {base_paths}")
        for b in base_paths:
            test_path = f"{b}/subiquity-umockdev-wrapper"
            log.debug(f"looking for {test_path=}")
            if os.path.isfile(test_path):
                script_path = test_path
                break

        log.debug(f"found {script_path=}")

        return script_path

    async def install_drivers(self, root_dir: str, context) -> None:
        # Copy config from live system, allowing changes made to the config
        # after it has been written to persist.
        copy_file_if_exists(
            self.dev_config_path,
            f"{root_dir}/{self.dev_config_path}",
        )

        # Copy wrapper script to target system
        # The "find and copy to /target/usr/bin" strategy is to get around
        # messing with $PATH on curtin in-target commands. When, or if, a more
        # standard way to run commands inside the target environment comes
        # along this should be converted to conform.
        wrapper_script_source: str | None = self._get_wrapper_path()
        if wrapper_script_source is None:
            raise Exception("Couldn't find path to subiquity-umockdev-wrapper")

        wrapper_script_dest: str = f"{root_dir}/usr/bin/subiquity-umockdev-wrapper"
        copy_file_if_exists(wrapper_script_source, wrapper_script_dest)
        os.chmod(wrapper_script_dest, 0o777)  # Make sure it's executable

        # Install wrapper script pre-reqs on target
        await run_curtin_command(
            self.app,
            context,
            "in-target",
            "-t",
            root_dir,
            "--",
            *self.pre_req_cmd,
            private_mounts=True,
        )

        # Finally call the wrapped install
        await super().install_drivers(root_dir, context)


class UbuntuDriversHasDriversInterface(UbuntuDriversInterface):
    """A dry-run implementation of ubuntu-drivers that returns a hard-coded
    list of drivers."""

    gpgpu_drivers: List[str] = ["nvidia-driver-470-server"]
    not_gpgpu_drivers: List[str] = ["nvidia-driver-510"]
    oem_metapackages: List[str] = ["oem-somerville-tentacool-meta"]

    def __init__(self, app, gpgpu: bool) -> None:
        super().__init__(app, gpgpu)
        self.drivers = self.gpgpu_drivers if gpgpu else self.not_gpgpu_drivers

    async def ensure_cmd_exists(self, root_dir: str) -> None:
        pass

    async def list_drivers(self, root_dir: str, context) -> List[str]:
        return self.drivers

    async def list_oem(self, root_dir: str, context) -> List[str]:
        return self.oem_metapackages


class UbuntuDriversNoDriversInterface(UbuntuDriversHasDriversInterface):
    """A dry-run implementation of ubuntu-drivers that returns a hard-coded
    empty list of drivers."""

    gpgpu_drivers: List[str] = []
    not_gpgpu_drivers: List[str] = []
    oem_metapackages: List[str] = []


class UbuntuDriversRunDriversInterface(UbuntuDriversInterface):
    """A dry-run implementation of ubuntu-drivers that actually runs the
    ubuntu-drivers command but locally."""

    def __init__(self, app, gpgpu: bool) -> None:
        super().__init__(app, gpgpu)

        if app.dr_cfg.ubuntu_drivers_run_on_host_umockdev is None:
            return

        self.list_oem_cmd = [
            "system_scripts/subiquity-umockdev-wrapper",
            "--config",
            app.dr_cfg.ubuntu_drivers_run_on_host_umockdev,
            "--",
        ] + self.list_oem_cmd

        self.list_drivers_cmd = [
            "system_scripts/subiquity-umockdev-wrapper",
            "--config",
            app.dr_cfg.ubuntu_drivers_run_on_host_umockdev,
            "--",
        ] + self.list_drivers_cmd

        self.install_drivers_cmd = [
            "system_scripts/subiquity-umockdev-wrapper",
            "--config",
            app.dr_cfg.ubuntu_drivers_run_on_host_umockdev,
            "--",
        ] + self.install_drivers_cmd

    async def ensure_cmd_exists(self, root_dir: str) -> None:
        # TODO This does not tell us if the "--recommended" option is
        # available.
        try:
            await arun_command(["sh", "-c", "command -v ubuntu-drivers"], check=True)
        except subprocess.CalledProcessError:
            raise CommandNotFoundError(
                "Command ubuntu-drivers is not available in this system"
            )

    async def list_drivers(self, root_dir: str, context) -> List[str]:
        # We run the command locally - ignoring the root_dir.
        result = await arun_command(self.list_drivers_cmd)
        return self._drivers_from_output(result.stdout)

    async def list_oem(self, root_dir: str, context) -> List[str]:
        # We run the command locally - ignoring the root_dir.
        result = await arun_command(self.list_oem_cmd)
        return self._oem_metapackages_from_output(result.stdout)


def get_ubuntu_drivers_interface(app) -> UbuntuDriversInterface:
    use_gpgpu = app.base_model.source.current.variant == "server"
    cls: Type[UbuntuDriversInterface] = UbuntuDriversClientInterface
    if app.opts.dry_run:
        if "no-drivers" in app.debug_flags:
            cls = UbuntuDriversNoDriversInterface
        elif "run-drivers" in app.debug_flags:
            cls = UbuntuDriversRunDriversInterface
        else:
            cls = UbuntuDriversHasDriversInterface

    if app.opts.kernel_cmdline.get("subiquity-fake-pci-devices"):
        log.debug("Using umockdev wrapper")
        cls = UbuntuDriversFakePCIDevicesInterface

    # For quickly testing MOK enrollment we install on server and force no gpgpu
    # The caveat to this is that it also has to be an online install
    if "subiquity-server-force-no-gpgpu" in app.opts.kernel_cmdline:
        log.debug("Forcing no gpgpu drivers. Requires online install on server.")
        use_gpgpu = False

    return cls(app, gpgpu=use_gpgpu)
