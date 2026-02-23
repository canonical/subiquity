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

import logging
from typing import Any, Dict, List, Optional, Union

import attr

from subiquitycore.lsb_release import lsb_release

log = logging.getLogger("subiquity.models.oem")


@attr.s(auto_attribs=True)
class OEMMetaPkg:
    name: str
    wants_oem_kernel: bool


class OEMModel:
    def __init__(self, *, dry_run: bool = False):
        # List of OEM metapackages relevant to the current hardware.
        # When the list is None, it has not yet been retrieved.
        self.metapkgs: Optional[List[OEMMetaPkg]] = None

        # Pre-26.04, OEM kernel install was off by default for server.  Set
        # this to enabled for 26.04+.
        # Desktop always has OEM kernel install on by default.
        # OEM kernels doesn't make sense for core, so disable there.
        self.install_on_defaults = {
            "server": False,
            "desktop": True,
            "core": False,
        }
        if lsb_release(dry_run=dry_run)["release"] >= "26.04":
            self.install_on_defaults["server"] = True

        # Should the OEM metapackages be installed on a given variant?
        self.install_on = self.install_on_defaults.copy()

        # has the user, by way of any supported mechanism (only autoinstall
        # today) indicated that we should or should not install the OEM
        # metapackages?  None implies that Subiquity chooses, dictated by
        # indexing into self.install_on using the install variant as the key.
        self.user_requested_install = None

    def make_autoinstall(self) -> Dict[str, Union[str, bool]]:
        if self.user_requested_install is None:
            return {"install": "auto"}
        else:
            return {"install": self.user_requested_install}

    def load_autoinstall_data(self, data: Dict[str, Any]) -> None:
        if data["install"] == "auto":
            self.install_on = self.install_on_defaults.copy()
            return

        self.user_requested_install = data["install"]
        self.install_on["server"] = data["install"]
        self.install_on["desktop"] = data["install"]
        # no matter what autoinstall says, we don't do OEM kernels on core.
