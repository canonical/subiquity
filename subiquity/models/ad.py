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
from typing import Optional

from subiquity.common.types import AdConnectionInfo

log = logging.getLogger("subiquity.models.ad")


class AdModel:
    """Models the Active Directory feature"""

    def __init__(self) -> None:
        self.do_join = False
        self.conn_info: Optional[AdConnectionInfo] = None

    def set(self, info: AdConnectionInfo):
        self.conn_info = info
        self.do_join = True

    def set_domain(self, domain: str):
        if not domain:
            return

        if self.conn_info:
            self.conn_info.domain_name = domain

        else:
            self.conn_info = AdConnectionInfo(domain_name=domain)

    async def target_packages(self):
        # NOTE Those packages must be present in the target system to allow
        # joining to a domain.
        if self.do_join:
            return ["adcli", "realmd", "sssd"]

        return []
