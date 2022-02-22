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

""" Module that defines helpers to use the ubuntu-drivers command. """

from abc import ABC, abstractmethod
import logging
import subprocess
from typing import List, Type

from subiquity.server.curtin import run_curtin_command
from subiquitycore.utils import arun_command


log = logging.getLogger("subiquity.server.ubuntu_drivers")


class CommandNotFoundError(Exception):
    """ Exception to be raised when the ubuntu-drivers command is not
    available.
    """


class UbuntuDriversInterface(ABC):
    def __init__(self, app, gpgpu: bool) -> None:
        self.app = app

        self.list_drivers_cmd = [
            "ubuntu-drivers", "list",
            "--recommended",
        ]
        self.install_drivers_cmd = [
            "ubuntu-drivers", "install",
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

    async def install_drivers(self, root_dir: str, context) -> None:
        await run_curtin_command(
            self.app, context,
            "in-target", "-t", root_dir, "--", *self.install_drivers_cmd)

    def _drivers_from_output(self, output: str) -> List[str]:
        """ Parse the output of ubuntu-drivers list --recommended and return a
        list of drivers. """
        drivers: List[str] = []
        # Drivers are listed one per line, but each driver is followed by a
        # linux-modules-* package (which we are not interested in showing).
        # e.g.,:
        # $ ubuntu-drivers list --recommended
        # nvidia-driver-470 linux-modules-nvidia-470-generic-hwe-20.04
        for line in [x.strip() for x in output.split("\n")]:
            if not line:
                continue
            drivers.append(line.split(" ", maxsplit=1)[0])

        return drivers


class UbuntuDriversClientInterface(UbuntuDriversInterface):
    """ UbuntuDrivers interface that uses the ubuntu-drivers command from the
    specified root directory. """

    async def ensure_cmd_exists(self, root_dir: str) -> None:
        # TODO This does not tell us if the "--recommended" option is
        # available.
        try:
            await self.app.command_runner.run(
                ['chroot', root_dir,
                 'sh', '-c',
                 "command -v ubuntu-drivers"])
        except subprocess.CalledProcessError:
            raise CommandNotFoundError(
                    f"Command ubuntu-drivers is not available in {root_dir}")

    async def list_drivers(self, root_dir: str, context) -> List[str]:
        result = await run_curtin_command(
            self.app, context,
            "in-target", "-t", root_dir, "--", *self.list_drivers_cmd,
            capture=True)
        # Currently we have no way to specify universal_newlines=True or
        # encoding="utf-8" to run_curtin_command so we need to decode the
        # output.
        return self._drivers_from_output(result.stdout.decode("utf-8"))


class UbuntuDriversHasDriversInterface(UbuntuDriversInterface):
    """ A dry-run implementation of ubuntu-drivers that returns a hard-coded
    list of drivers. """
    gpgpu_drivers: List[str] = ["nvidia-driver-470-server"]
    not_gpgpu_drivers: List[str] = ["nvidia-driver-510"]

    def __init__(self, app, gpgpu: bool) -> None:
        super().__init__(app, gpgpu)
        self.drivers = self.gpgpu_drivers if gpgpu else self.not_gpgpu_drivers

    async def ensure_cmd_exists(self, root_dir: str) -> None:
        pass

    async def list_drivers(self, root_dir: str, context) -> List[str]:
        return self.drivers


class UbuntuDriversNoDriversInterface(UbuntuDriversHasDriversInterface):
    """ A dry-run implementation of ubuntu-drivers that returns a hard-coded
    empty list of drivers. """

    gpgpu_drivers: List[str] = []
    not_gpgpu_drivers: List[str] = []


class UbuntuDriversRunDriversInterface(UbuntuDriversInterface):
    """ A dry-run implementation of ubuntu-drivers that actually runs the
    ubuntu-drivers command but locally. """
    async def ensure_cmd_exists(self, root_dir: str) -> None:
        # TODO This does not tell us if the "--recommended" option is
        # available.
        try:
            await arun_command(["command", "-v", "ubuntu-drivers"])
        except subprocess.CalledProcessError:
            raise CommandNotFoundError(
                    "Command ubuntu-drivers is not available in this system")

    async def list_drivers(self, root_dir: str, context) -> List[str]:
        # We run the command locally - ignoring the root_dir.
        result = await arun_command(self.list_drivers_cmd)
        return self._drivers_from_output(result.stdout)


def get_ubuntu_drivers_interface(app) -> UbuntuDriversInterface:
    is_server = app.base_model.source.current.variant == "server"
    cls: Type[UbuntuDriversInterface] = UbuntuDriversClientInterface
    if app.opts.dry_run:
        if 'has-drivers' in app.debug_flags:
            cls = UbuntuDriversHasDriversInterface
        elif 'run-drivers' in app.debug_flags:
            cls = UbuntuDriversRunDriversInterface
        else:
            cls = UbuntuDriversNoDriversInterface

    return cls(app, gpgpu=is_server)
