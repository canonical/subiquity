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

from subiquity.common.pkg import TargetPkg

log = logging.getLogger("subiquity.models.drivers")


class DriversModel:
    do_install = False
    fake_pci_devices: bool = False

    async def target_packages(self) -> list[TargetPkg]:
        if self.fake_pci_devices:
            return [
                TargetPkg(name="umockdev", skip_when_offline=False),
                TargetPkg(name="gir1.2-umockdev-1.0", skip_when_offline=False),
            ]
        else:
            return []

    async def live_packages(self) -> tuple[set, set]:
        before = set()
        during = set()
        if self.fake_pci_devices:
            before.add("umockdev")
            before.add("gir1.2-umockdev-1.0")
        return (before, during)
