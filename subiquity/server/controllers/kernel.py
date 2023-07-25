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

from subiquity.server.controller import NonInteractiveController
from subiquity.server.kernel import flavor_to_pkgname

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
                self.model.explicitly_requested = True
                log.debug(f"Using kernel {kernel_package} due to {mp_file}")
                break
        else:
            log.debug("Using default kernel linux-generic")
            self.model.metapkg_name = "linux-generic"

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
        self.model.explicitly_requested = True

    def make_autoinstall(self):
        return {"package": self.model.metapkg_name}
