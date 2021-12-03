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
""" Module defining the server-side controller class for Ubuntu Advantage. """

import logging

from subiquity.common.apidef import API
from subiquity.common.types import UbuntuAdvantageInfo
from subiquity.server.controller import SubiquityController

log = logging.getLogger("subiquity.server.controllers.ubuntu_advantage")


class UbuntuAdvantageController(SubiquityController):
    """ Represent the server-side Ubuntu Advantage controller. """

    endpoint = API.ubuntu_advantage

    model_name = "ubuntu_advantage"

    def serialize(self) -> str:
        """ Save the current state of the model so it can be loaded later.
        Currently this function is called automatically by .configured().
        """
        return self.model.token

    def deserialize(self, token: str) -> None:
        """ Loads the last-known state of the model. """
        self.model.token = token

    async def GET(self) -> UbuntuAdvantageInfo:
        """ Handle a GET request coming from the client-side controller. """
        return UbuntuAdvantageInfo(token=self.model.token)

    async def POST(self, data: UbuntuAdvantageInfo):
        """ Handle a POST request coming from the client-side controller and
        then call .configured().
        """
        log.debug("Received POST: %s", data)
        self.model.token = data.token
        await self.configured()
