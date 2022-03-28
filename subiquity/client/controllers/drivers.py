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

import asyncio
import logging
from typing import List

from subiquitycore.tuicontroller import Skip

from subiquity.common.types import DriversPayload, DriversResponse
from subiquity.client.controller import SubiquityTuiController
from subiquity.ui.views.drivers import DriversView, DriversViewStatus

log = logging.getLogger('subiquity.client.controllers.drivers')


class DriversController(SubiquityTuiController):

    endpoint_name = 'drivers'

    async def make_ui(self) -> DriversView:
        response: DriversResponse = await self.endpoint.GET()
        if not response.drivers and response.drivers is not None:
            raise Skip
        return DriversView(self, response.drivers, response.install)

    async def _wait_drivers(self) -> List[str]:
        response: DriversResponse = await self.endpoint.GET(wait=True)
        assert response.drivers is not None
        return response.drivers

    async def run_answers(self):
        if 'install' not in self.answers:
            return

        from subiquitycore.testing.view_helpers import (
            click,
        )

        view = self.app.ui.body
        while view.status == DriversViewStatus.WAITING:
            await asyncio.sleep(0.2)
        if view.status == DriversViewStatus.NO_DRIVERS:
            click(view.cont_btn.base_widget)
            return

        view.form.install.value = self.answers['install']

        click(view.form.done_btn.base_widget)

    def cancel(self) -> None:
        self.app.prev_screen()

    def done(self, install: bool) -> None:
        log.debug("DriversController.done next_screen install=%s", install)
        self.app.next_screen(
                self.endpoint.POST(DriversPayload(install=install)))
