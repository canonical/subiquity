# Copyright 2024 Canonical, Ltd.
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

from subiquity.client.controller import SubiquityTuiController
from subiquity.ui.views.homenode_token import HomenodeTokenView

log = logging.getLogger("subiquity.client.controllers.homenode_token")


class HomenodeTokenController(SubiquityTuiController):
    endpoint_name = "homenode_token"

    async def make_ui(self):
        token = await self.endpoint.GET()
        return HomenodeTokenView(self, token)

    def cancel(self):
        self.app.request_prev_screen()

    def done(self, token):
        log.debug("HomenodeTokenController.done next_screen token=%s", token)
        self.app.request_next_screen(self.endpoint.POST(token))

