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

import asyncio
import logging

import aiohttp

from subiquitycore.tuicontroller import (
    Skip,
    )

from subiquity.common.types import (
    RefreshCheckState,
    )
from subiquity.client.controller import (
    SubiquityTuiController,
    )
from subiquity.ui.views.refresh import RefreshView


log = logging.getLogger('subiquity.client.controllers.refresh')


class RefreshController(SubiquityTuiController):

    endpoint_name = 'refresh'

    def __init__(self, app):
        super().__init__(app)
        self.offered_first_time = False

    async def get_progress(self, change):
        while True:
            try:
                return await self.endpoint.progress.GET(change_id=change)
            except aiohttp.ClientError:
                # Probably the server is restarting.
                await asyncio.sleep(1)

    async def make_ui(self, index=1):
        if self.app.updated:
            raise Skip()
        show = False
        self.status = await self.endpoint.GET()
        if index == 1:
            if self.status.availability == RefreshCheckState.AVAILABLE:
                show = True
                self.offered_first_time = True
        elif index == 2:
            if not self.offered_first_time:
                if self.status.availability in [RefreshCheckState.UNKNOWN,
                                                RefreshCheckState.AVAILABLE]:
                    show = True
        else:
            raise AssertionError("unexpected index {}".format(index))
        if show:
            return RefreshView(self)
        else:
            raise Skip()

    async def wait_for_check(self):
        self.status = await self.endpoint.GET(wait=True)
        return self.status

    async def start_update(self):
        return await self.endpoint.POST()

    def run_answers(self):
        # Handled in the view
        pass

    def done(self, sender=None):
        log.debug("RefreshController.done next_screen")
        self.app.next_screen()

    def cancel(self, sender=None):
        self.app.prev_screen()
