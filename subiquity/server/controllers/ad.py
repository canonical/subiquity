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

from subiquity.common.apidef import API
from subiquity.common.types import ADConnectionInfo, ADValidationResult
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.ad')


class ADController(SubiquityController):
    """ Implements the server part of the Active Directory feature. """
    model_name = "ad"
    endpoint = API.active_directory
    # No auto install key and schema for now due password handling uncertainty.

    async def GET(self) -> Optional[ADConnectionInfo]:
        """Returns the currently configured AD settings"""
        return self.model.conn_info

    async def POST(self, data: ADConnectionInfo) -> List[ADValidationResult]:
        self.model.conn_info = data
        await self.configured()
        return [ADValidationResult.OK]
