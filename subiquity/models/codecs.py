# Copyright 2022 Canonical, Ltd.
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
from typing import List

from subiquity.common.pkg import TargetPkg

log = logging.getLogger("subiquity.models.codecs")


class CodecsModel:
    do_install = False

    async def target_packages(self) -> List[TargetPkg]:
        # NOTE currently, ubuntu-restricted-addons is an empty package that
        # pulls relevant packages through Recommends: Ideally, we should make
        # sure to run the APT command for this package with the
        # --install-recommends option.
        if not self.do_install:
            return []

        return [TargetPkg(name="ubuntu-restricted-addons", skip_when_offline=True)]
