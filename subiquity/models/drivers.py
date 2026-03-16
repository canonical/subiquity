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

log = logging.getLogger("subiquity.models.drivers")


class DriversModel:
    def __init__(self):
        self.do_install = False

        # Drivers that have been offered by ubuntu-drivers.
        # None means that the list has not (yet) been retrieved whereas an
        # empty list means that no drivers are available.
        self.deb_drivers: list[str] | None = None
