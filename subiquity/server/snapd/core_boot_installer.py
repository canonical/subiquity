# Copyright 2026 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Implementation of the snapd "core boot" / TPM-FDE system install steps.

These steps (storage-encryption setup, recovery-key generation, finalizing
the install and preseeding the snapd seed in the target) are install-phase
operations that talk to snapd's /v2/systems/<label> API.
"""

import logging
import pathlib
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Callable

import attrs

from subiquity.server.mounter import Mounter
from subiquity.server.snapd import api as snapdapi
from subiquity.server.snapd import types as snapdtypes
from subiquitycore.context import with_context

if TYPE_CHECKING:
    from subiquity.server.controllers.storage import VariationInfo

log = logging.getLogger("subiquity.server.snapd.core_boot_installer")


@attrs.define
class CoreBootInstallData:
    """Bridge data shared between the storage controller and the installer.

    Produced by the storage controller once a core-boot classic (TPM/FDE)
    guided choice has been applied, and passed to CoreBootInstaller for the
    install-phase snapd steps."""

    info: "VariationInfo"
    on_volume: snapdtypes.OnVolume | None
    volumes_auth: snapdtypes.VolumesAuth | None


class CoreBootInstaller:
    """Implement the snapd system install steps for a core-boot classic
    install.
    """

    def __init__(self, app, data: CoreBootInstallData) -> None:
        self.app = app
        self.data: CoreBootInstallData = data

    def _on_volumes(self) -> dict[str, snapdtypes.OnVolume]:
        # Return a value suitable for use as the 'on-volumes' part of a
        # SystemActionRequest.
        #
        # This must be run after curtin partitioning, which will result in a
        # call to update_devices which will have set .path on all block
        # devices.
        [key] = self.data.info.system.volumes.keys()
        return {key: self.data.on_volume}

    @with_context(description="configuring TPM-backed full disk encryption")
    async def setup_encryption(
        self,
        context,
        apply_encrypted_devices: Callable[[dict[snapdtypes.Role, str]], None],
    ) -> None:
        label = self.data.info.label
        kwargs = dict(
            action=snapdtypes.SystemAction.INSTALL,
            step=snapdtypes.SystemActionStep.SETUP_STORAGE_ENCRYPTION,
            on_volumes=self._on_volumes(),
        )
        if self.data.volumes_auth is not None:
            kwargs["volumes_auth"] = self.data.volumes_auth
        # This is required to have the proper keyboard layout on first boot
        # before typing the passphrase.
        # Only supported since 2.76 but ignored on older versions.
        kwargs["keyboard_config"] = snapdtypes.KeyboardConfig.from_subiquity_kb_model(
            self.app.base_model.keyboard
        )
        result = await snapdapi.post_and_wait(
            self.app.snapdapi,
            self.app.snapdapi.v2.systems[label].POST,
            snapdtypes.SystemActionRequest(**kwargs),
            ann=snapdtypes.SystemActionResponseSetupEncryption,
        )
        apply_encrypted_devices(result.encrypted_devices)

    async def fetch_core_boot_recovery_key(self) -> str:
        """Fetch the recovery key from snapd and return it.

        The caller is responsible for storing the key on the storage model.
        """
        label = self.data.info.label

        result = await self.app.snapdapi.v2.systems[label].POST(
            snapdtypes.SystemActionRequest(
                action=snapdtypes.SystemAction.INSTALL,
                step=snapdtypes.SystemActionStep.GENERATE_RECOVERY_KEY,
                on_volumes={},
            ),
            return_type=snapdtypes.SystemActionResponseGenerateRecoveryKey,
        )

        return result.recovery_key

    async def target_preseed(self, target: pathlib.Path) -> None:
        async with AsyncExitStack() as es:
            # Bind-mount required filesystems
            # Some of these might already be mounted by curtin, but
            # it should be fine to bind-mount twice.
            mounter = Mounter(self.app)

            to_bind_mount = [
                "dev",
                "proc",
                "sys",
                "sys/kernel/security",
                "var/lib/snapd/seed",
            ]

            for fs in to_bind_mount:
                # Needed at least for var/lib/snapd/seed in dry-run mode.
                (target / fs).parent.mkdir(parents=True, exist_ok=True)

                await es.enter_async_context(
                    mounter.bind_mounted(pathlib.Path("/") / fs, target / fs)
                )

            await snapdapi.post_and_wait(
                self.app.snapdapi,
                self.app.snapdapi.v2.systems[self.data.info.label].POST,
                snapdtypes.SystemActionRequest(
                    action=snapdtypes.SystemAction.INSTALL,
                    step=snapdtypes.SystemActionStep.PRESEED,
                    target_root=str(target),
                ),
            )

    @with_context(description="making system bootable")
    async def finish_install(self, context, kernel_components: list[str]) -> None:
        log.debug(f"finish_install: {kernel_components=}")
        label = self.data.info.label
        kernels = self.data.info.system.model.snaps_of_type(
            snapdtypes.ModelSnapType.KERNEL
        )
        if len(kernels) == 1:
            optional_snaps = []
            if (optionals := self.data.info.system.available_optional) is not None:
                optional_snaps = optionals.snaps

            optional_install = snapdtypes.OptionalInstall(
                components={kernels[0].name: kernel_components},
                snaps=optional_snaps,
            )
        else:
            log.error(f"unexpected number of kernel snaps {len(kernels)}")
            # multi-kernel model case unknown, let snapd try to install all
            # optional things here.
            optional_install = snapdtypes.OptionalInstall(all=True)
        log.debug(f"finish_install: {optional_install=}")

        await snapdapi.post_and_wait(
            self.app.snapdapi,
            self.app.snapdapi.v2.systems[label].POST,
            snapdtypes.SystemActionRequest(
                action=snapdtypes.SystemAction.INSTALL,
                step=snapdtypes.SystemActionStep.FINISH,
                on_volumes=self._on_volumes(),
                optional_install=optional_install,
            ),
        )
