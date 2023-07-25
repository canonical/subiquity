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

log = logging.getLogger("subiquity.models.oem")


@attr.s(auto_attribs=True)
class OEMMetaPkg:
    name: str
    wants_oem_kernel: bool


class OEMModel:
    def __init__(self):
        # List of OEM metapackages relevant to the current hardware.
        # When the list is None, it has not yet been retrieved.
        self.metapkgs: Optional[List[OEMMetaPkg]] = None

        # By default, skip looking for OEM meta-packages if we are running
        # ubuntu-server. OEM meta-packages expect the default kernel flavor to
        # be HWE (which is only true for ubuntu-desktop).
        self.install_on = {
            "server": False,
            "desktop": True,
            "core": False,
        }

    def make_autoinstall(self) -> Dict[str, Union[str, bool]]:
        server = self.install_on["server"]
        desktop = self.install_on["desktop"]

        if server and desktop:
            return {"install": True}
        if not server and not desktop:
            return {"install": False}

        # Having server = True and desktop = False is not supported.
        assert desktop and not server

        return {"install": "auto"}

    def load_autoinstall_data(self, data: Dict[str, Any]) -> None:
        if data["install"] == "auto":
            self.install_on["server"] = False
            self.install_on["desktop"] = True
            return

        self.install_on["server"] = data["install"]
        self.install_on["desktop"] = data["install"]
