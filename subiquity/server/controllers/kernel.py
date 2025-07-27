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

import logging
import os

from subiquity.models.source import BridgeKernelReason
from subiquity.server.controller import NonInteractiveController
from subiquity.server.kernel import flavor_to_pkgname
from subiquity.server.types import InstallerChannels

log = logging.getLogger("subiquity.server.controllers.kernel")


class KernelController(NonInteractiveController):
    model_name = autoinstall_key = "kernel"
    autoinstall_default = None
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "package": {"type": "string"},
            "flavor": {"type": "string"},
        },
        "oneOf": [
            {
                "type": "object",
                "required": ["package"],
            },
            {
                "type": "object",
                "required": ["flavor"],
            },
        ],
    }

    def start(self):
        if self.model.metapkg_name is not None:
            # if we're exiting early here, we have made a decision on the
            # kernel already - probably autoinstall - and are skipping the
            # bridge_kernel logic.  We must still broadcast
            # BRIDGE_KERNEL_DECIDED though, otherwise we'll hang in
            # curtin_install before curthooks waiting for
            # bridge_kernel_decided.set().
            self.app.hub.broadcast(InstallerChannels.BRIDGE_KERNEL_DECIDED)
            # if we have set the desired kernel already, use that.
            return
        # the ISO may have been configured to tell us what kernel to use
        # /run is the historical location, but a bit harder to craft an ISO to
        # have it there as it needs to be populated at runtime.
        run_mp_file = os.path.join(self.app.base_model.root, "run/kernel-meta-package")
        etc_mp_file = os.path.join(
            self.app.base_model.root, "etc/subiquity/kernel-meta-package"
        )
        for mp_file in (run_mp_file, etc_mp_file):
            if os.path.exists(mp_file):
                with open(mp_file) as fp:
                    kernel_package = fp.read().strip()
                self.model.metapkg_name = kernel_package
                self.default_metapkg_name = self.model.metapkg_name
                # built-in kernel requirements are not considered
                # explicitly_requested
                self.model.explicitly_requested = False
                log.debug(f"Using kernel {kernel_package} due to {mp_file}")
                break
        else:
            # no default kernel found in etc or run, use default from
            # source catalog.
            self.app.hub.subscribe(
                (InstallerChannels.CONFIGURED, "source"), self._set_source
            )
        self.needs_bridge = {}
        self.app.hub.subscribe(
            InstallerChannels.INSTALL_CONFIRMED,
            self._confirmed,
        )
        self.app.hub.subscribe(
            InstallerChannels.DRIVERS_DECIDED,
            self._drivers_decided,
        )

    async def _set_source(self):
        self.model.metapkg_name = self.app.base_model.source.catalog.kernel.default
        self.default_metapkg_name = self.model.metapkg_name

    def _maybe_set_bridge_kernel(self, reason, value):
        if reason in self.needs_bridge:
            return
        reasons = self.app.base_model.source.catalog.kernel.bridge_reasons
        if reason not in reasons:
            value = False
        self.needs_bridge[reason] = value
        if len(self.needs_bridge) < len(BridgeKernelReason):
            return
        log.debug("bridge kernel decided %s", self.needs_bridge)
        if any(self.needs_bridge.values()):
            self.model.metapkg_name = self.app.base_model.source.catalog.kernel.bridge
        else:
            self.model.metapkg_name = self.default_metapkg_name
        self.app.hub.broadcast(InstallerChannels.BRIDGE_KERNEL_DECIDED)

    def _confirmed(self):
        fs_model = self.app.base_model.filesystem
        if not self.app.base_model.source.catalog.kernel.bridge_reasons:
            self.app.hub.broadcast(InstallerChannels.BRIDGE_KERNEL_DECIDED)
        self._maybe_set_bridge_kernel(BridgeKernelReason.ZFS, fs_model.uses_zfs())
        if not self.app.base_model.source.search_drivers:
            self._maybe_set_bridge_kernel(BridgeKernelReason.DRIVERS, False)

    def _drivers_decided(self):
        drivers_controller = self.app.controllers.Drivers
        # while the term DRIVERS is used here, only some drivers are expected
        # to trigger bridge kernel fallback, and only then if DRIVERS is listed
        # as one of the bridge_reasons.
        self._maybe_set_bridge_kernel(
            BridgeKernelReason.DRIVERS,
            drivers_controller.model.do_install
            and any("nvidia" in driver for driver in drivers_controller.drivers),
        )

    def load_autoinstall_data(self, data):
        if data is None:
            return
        package = data.get("package")
        flavor = data.get("flavor")
        if package is None:
            dry_run: bool = self.app.opts.dry_run
            if flavor is None:
                flavor = "generic"
            package = flavor_to_pkgname(flavor, dry_run=dry_run)
        log.debug(f"Using kernel {package} due to autoinstall")
        self.model.metapkg_name = package
        # autoinstall kernel requirements are explicitly_requested
        self.model.explicitly_requested = True

    def make_autoinstall(self):
        return {"package": self.model.metapkg_name}
