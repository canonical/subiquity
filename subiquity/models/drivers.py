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
import re

log = logging.getLogger("subiquity.models.drivers")


class DriversModel:
    def __init__(self):
        self.do_install = False

        # Drivers that have been offered by ubuntu-drivers.
        # None means that the list has not (yet) been retrieved whereas an
        # empty list means that no drivers are available.
        self.deb_drivers: list[str] | None = None

    def matching_kernel_components(self, kernel_components: list[str]) -> list[str]:
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

        # Any variation of server and open driver is deliberately mapped to
        # what we have.
        for driver in sorted(self.deb_drivers, reverse=True):
            m = re.fullmatch("nvidia-driver-([0-9]+)(-server)?(-open)?", driver)
            if not m:
                continue
            nvidia_driver_offered = True
            ver = m.group(1)
            for branch in ("uda", "erd"):
                ko = f"nvidia-{ver}-{branch}-ko"
                user = f"nvidia-{ver}-{branch}-user"
                if ko in kernel_components and user in kernel_components:
                    return [ko, user]

        # if we don't match there, accept the newest reasonable version
        if nvidia_driver_offered:
            for component in sorted(kernel_components, reverse=True):
                m = re.fullmatch("nvidia-([0-9]+)-([a-z]+)-ko", component)
                if not m:
                    continue
                ko = component
                ver = m.group(1)
                branch = m.group(2)
                user = f"nvidia-{ver}-{branch}-user"
                if user in kernel_components:
                    return [ko, user]
        return []
