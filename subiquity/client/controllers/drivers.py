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

from subiquitycore.tuicontroller import Skip

from subiquity.client.controller import SubiquityTuiController
from subiquity.ui.views.drivers import DriversView

log = logging.getLogger('subiquity.client.controllers.drivers')


class DriversController(SubiquityTuiController):

    endpoint_name = 'drivers'

    async def make_ui(self):
        has_drivers = await self.endpoint.GET()
        if has_drivers is False:
            raise Skip
        return DriversView(self, has_drivers)

    async def _wait_drivers(self):
        return await self.endpoint.GET(wait=True)

    def run_answers(self):
        if 'drivers' in self.answers:
            self.done(self.answers['drivers'])

    def cancel(self):
        self.app.prev_screen()

    def done(self, install):
        log.debug("DriversController.done next_screen install=%s", install)
        self.app.next_screen(self.endpoint.POST(install))
