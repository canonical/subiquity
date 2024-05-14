# Copyright 2015 Canonical, Ltd.
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
import subprocess
from typing import List

from subiquity import cloudinit
from subiquity.common.pkg import TargetPkg
from subiquitycore.models.network import NetworkModel as CoreNetworkModel
from subiquitycore.utils import arun_command

log = logging.getLogger("subiquity.models.network")


class NetworkModel(CoreNetworkModel):
    def __init__(self):
        super().__init__("subiquity")
        self.override_config = None

    def render_config(self):
        if self.override_config is not None:
            return self.override_config
        else:
            return super().render_config()

    def render(self):
        netplan = self.render_config()
        # If host cloud-init version has no readable combined-cloud-config,
        # default to False.
        cloud_cfg = cloudinit.get_host_combined_cloud_config()
        use_cloudinit_net = cloud_cfg.get("features", {}).get(
            "NETPLAN_CONFIG_ROOT_READ_ONLY", False
        )

        if use_cloudinit_net:
            r = {
                "write_files": {
                    "etc_netplan_installer": {
                        "path": "etc/cloud/cloud.cfg.d/90-installer-network.cfg",
                        "content": self.stringify_config(netplan),
                        "permissions": "0600",
                    },
                }
            }
        else:
            r = {
                "write_files": {
                    # Disable cloud-init networking
                    "no_cloudinit_net": {
                        "path": (
                            "etc/cloud/cloud.cfg.d/"
                            "subiquity-disable-cloudinit-networking.cfg"
                        ),
                        "content": "network: {config: disabled}\n",
                        "permissions": "0600",
                    },
                    "etc_netplan_installer": {
                        "path": "etc/netplan/00-installer-config.yaml",
                        "content": self.stringify_config(netplan),
                        "permissions": "0600",
                    },
                },
            }
        return r

    async def target_packages(self) -> List[TargetPkg]:
        if not self.needs_wpasupplicant:
            return []

        return [TargetPkg(name="wpasupplicant", skip_when_offline=False)]

    async def is_nm_enabled(self):
        try:
            cp = await arun_command(("nmcli", "networking"), check=True)
        except subprocess.CalledProcessError as exc:
            log.warning(
                "failed to run nmcli networking, considering NetworkManager disabled."
            )
            log.debug("stderr: %s", exc.stderr)
            return False
        except FileNotFoundError:
            return False

        return cp.stdout == "enabled\n"
