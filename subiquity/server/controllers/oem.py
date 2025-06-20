# Copyright 2023 Canonical, Ltd.
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
import logging
from typing import List, Optional

from subiquity.common.apidef import API
from subiquity.common.types import OEMResponse
from subiquity.models.oem import OEMMetaPkg
from subiquity.server.apt import OverlayCleanupError
from subiquity.server.autoinstall import AutoinstallError
from subiquity.server.controller import SubiquityController
from subiquity.server.curtin import run_curtin_command
from subiquity.server.kernel import flavor_to_pkgname
from subiquity.server.types import InstallerChannels
from subiquity.server.ubuntu_drivers import (
    CommandNotFoundError,
    get_ubuntu_drivers_interface,
)
from subiquitycore.context import with_context

log = logging.getLogger("subiquity.server.controllers.oem")


class OEMController(SubiquityController):
    endpoint = API.oem

    autoinstall_key = model_name = "oem"
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "install": {
                "oneOf": [
                    {
                        "type": "boolean",
                    },
                    {
                        "type": "string",
                        "const": "auto",
                    },
                ],
            },
        },
        "required": ["install"],
    }
    autoinstall_default = {"install": "auto"}

    def __init__(self, app) -> None:
        super().__init__(app)
        # At this point, the source variant has not been selected but it only
        # has an impact if we're listing drivers, not OEM metapackages.
        self.ubuntu_drivers = get_ubuntu_drivers_interface(self.app)

        self.load_metapkgs_task: Optional[asyncio.Task] = None
        self.kernel_configured_event = asyncio.Event()
        self.fs_configured_event = asyncio.Event()

    def start(self) -> None:
        self._wait_confirmation = asyncio.Event()
        self.app.hub.subscribe(
            InstallerChannels.INSTALL_CONFIRMED, self._wait_confirmation.set
        )
        self._wait_apt = asyncio.Event()
        self.app.hub.subscribe(InstallerChannels.APT_CONFIGURED, self._wait_apt.set)
        self.app.hub.subscribe(
            (InstallerChannels.CONFIGURED, "kernel"), self.kernel_configured_event.set
        )
        self.app.hub.subscribe(
            (InstallerChannels.CONFIGURED, "filesystem"), self.fs_configured_event.set
        )

        async def list_and_mark_configured() -> None:
            await self.load_metapackages_list()
            await self.ensure_no_kernel_conflict()
            await self.configured()

        self.load_metapkgs_task = asyncio.create_task(list_and_mark_configured())

    def make_autoinstall(self):
        return self.model.make_autoinstall()

    def load_autoinstall_data(self, *args, **kwargs) -> None:
        self.model.load_autoinstall_data(*args, **kwargs)

    async def wants_oem_kernel(self, pkgname: str, *, context, overlay) -> bool:
        """For a given package, tell whether it wants the OEM or the default
        kernel flavor. We look for the Ubuntu-Oem-Kernel-Flavour attribute in
        the package meta-data. If the attribute is present and has the value
        "default", then return False. Otherwise, return True."""
        result = await run_curtin_command(
            self.app,
            context,
            "in-target",
            "-t",
            overlay.mountpoint,
            "--",
            "apt-cache",
            "show",
            pkgname,
            capture=True,
            private_mounts=True,
        )
        for line in result.stdout.decode("utf-8").splitlines():
            if not line.startswith("Ubuntu-Oem-Kernel-Flavour:"):
                continue

            flavor = line.split(":", maxsplit=1)[1].strip()
            if flavor == "default":
                return False
            elif flavor == "oem":
                return True
            else:
                log.warning("%s wants unexpected kernel flavor: %s", pkgname, flavor)
                return True

        log.warning("%s has no Ubuntu-Oem-Kernel-Flavour", pkgname)
        return True

    @with_context()
    async def load_metapackages_list(self, context) -> None:
        with context.child("wait_confirmation"):
            await self._wait_confirmation.wait()
        # In normal scenarios, the confirmation event comes after the
        # storage/filesystem is configured. However, in semi automated desktop
        # installs (especially in CI), it is possible that the events come in
        # the reverse order. Let's be prepared for it by also waiting for the
        # storage configured event.
        await self.fs_configured_event.wait()

        # Only look for OEM meta-packages on supported variants and if we are
        # not running core boot.
        variant: str = self.app.base_model.source.current.variant
        fs_controller = self.app.controllers.Filesystem
        if fs_controller.is_core_boot_classic():
            log.debug("listing of OEM meta-packages disabled on core boot classic")
            self.model.metapkgs = []
            return
        if not self.model.install_on[variant]:
            log.debug("listing of OEM meta-packages disabled on %s", variant)
            self.model.metapkgs = []
            return

        with context.child("wait_apt"):
            await self._wait_apt.wait()

        apt = self.app.controllers.Mirror.final_apt_configurer
        try:
            async with apt.overlay() as d:
                try:
                    # Make sure ubuntu-drivers is available.
                    await self.ubuntu_drivers.ensure_cmd_exists(d.mountpoint)
                except CommandNotFoundError:
                    self.model.metapkgs = []
                else:
                    metapkgs: List[str] = await self.ubuntu_drivers.list_oem(
                        root_dir=d.mountpoint, context=context
                    )
                    self.model.metapkgs = [
                        OEMMetaPkg(
                            name=name,
                            wants_oem_kernel=await self.wants_oem_kernel(
                                name, context=context, overlay=d
                            ),
                        )
                        for name in metapkgs
                    ]

        except OverlayCleanupError:
            log.exception("Failed to cleanup overlay. Continuing anyway.")

        for pkg in self.model.metapkgs:
            if pkg.wants_oem_kernel:
                kernel_model = self.app.base_model.kernel
                # flavor_to_pkgname expects a value such as "oem", "generic",
                # or "generic-hwe", not a package name in any case.
                # The return value of the function should look something like
                # linux-oem-24.04
                kernel_model.metapkg_name_override = flavor_to_pkgname(
                    "oem", dry_run=self.app.opts.dry_run
                )

                log.debug(
                    'overriding kernel flavor to "oem" according to the OEM metapkg info'
                )

        log.debug("OEM meta-packages to install: %s", self.model.metapkgs)

    async def ensure_no_kernel_conflict(self) -> None:
        kernel_model = self.app.base_model.kernel

        await self.kernel_configured_event.wait()

        if self.model.metapkgs:
            for metapkg in self.model.metapkgs:
                if kernel_model.metapkg_name == metapkg.name:
                    # The below check handles conflicts with autoinstall / oem
                    # kernel requirements, but if they're asking for the same
                    # thing, there is no conflict.  We look at the raw
                    # metapkg_name and not needed_kernel because we want the
                    # autoinstall value if it's there, not the overridden value
                    # set by the OEM code.
                    return
            if kernel_model.explicitly_requested:
                msg = _(
                    """\
A specific kernel flavor was requested but it cannot be satistified when \
installing on certified hardware.
You should either disable the installation of OEM meta-packages using the \
following autoinstall snippet or let the installer decide which kernel to
install.
  oem:
    install: false
"""
                )
                raise AutoinstallError(msg)

    @with_context()
    async def apply_autoinstall_config(self, context) -> None:
        await self.load_metapkgs_task
        await self.ensure_no_kernel_conflict()

    async def GET(self, wait: bool = False) -> OEMResponse:
        if wait:
            await asyncio.shield(self.load_metapkgs_task)
        if self.model.metapkgs is None:
            metapkgs = None
        else:
            metapkgs = [pkg.name for pkg in self.model.metapkgs]
        return OEMResponse(metapackages=metapkgs)
