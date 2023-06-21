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
from typing import List, Optional

import attr

log = logging.getLogger('subiquity.models.oem')


@attr.s(auto_attribs=True)
class OEMMetaPkg:
    name: str
    wants_oem_kernel: bool


class OEMModel:
    def __init__(self):
        # List of OEM metapackages relevant to the current hardware.
        # When the list is None, it has not yet been retrieved.
        self.metapkgs: Optional[List[OEMMetaPkg]] = None
