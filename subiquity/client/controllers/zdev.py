# Copyright 2019 Canonical, Ltd.
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
from subiquity.ui.views import ZdevView


log = logging.getLogger("subiquity.client.controllers.zdev")


class ZdevController(SubiquityTuiController):

    endpoint_name = 'zdev'

    async def make_ui(self):
        infos = await self.endpoint.GET()
        return ZdevView(self, infos)

    def run_answers(self):
        if 'accept-default' in self.answers:
            self.done()

    def cancel(self):
        self.app.prev_screen()

    def done(self):
        # switch to next screen
        self.app.next_screen()

    async def chzdev(self, action, zdevinfo):
        return await self.endpoint.chzdev.POST(action, zdevinfo)
