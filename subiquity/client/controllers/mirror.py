# Copyright 2018 Canonical, Ltd.
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

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.types import MirrorCheckStatus, MirrorGet, MirrorPost
from subiquity.ui.views.mirror import MirrorView
from subiquitycore.tuicontroller import Skip

log = logging.getLogger("subiquity.client.controllers.mirror")


class MirrorController(SubiquityTuiController):
    endpoint_name = "mirror"

    async def make_ui(self):
        mirror_response: MirrorGet = await self.endpoint.GET()
        if not mirror_response.relevant:
            raise Skip
        # We could do all sort of things with the list of candidate mirrors in
        # the UI ; like suggesting the next mirror automatically if the first
        # candidate fails. For now, we keep things simple.
        if mirror_response.elected is not None:
            url = mirror_response.elected
        elif mirror_response.staged:
            url = mirror_response.staged
        else:
            # Just in case there is no candidate at all.
            # In practise, it should seldom happen.
            url = next(iter(mirror_response.candidates), "")
        has_network = await self.app.client.network.has_network.GET()
        if has_network:
            check = await self.endpoint.check_mirror.progress.GET()
        else:
            check = None
        return MirrorView(self, url, check=check, has_network=has_network)

    async def run_answers(self):
        async def wait_mirror_check() -> None:
            """Wait until the mirror check has finished running."""
            while True:
                last_status = self.app.ui.body.last_status
                if last_status not in [None, MirrorCheckStatus.RUNNING]:
                    return
                await asyncio.sleep(0.1)

        if "mirror" in self.answers:
            self.app.ui.body.form.url.value = self.answers["mirror"]
            await wait_mirror_check()
            self.app.ui.body.form._click_done(None)
        elif "country-code" in self.answers or "accept-default" in self.answers:
            await wait_mirror_check()
            self.app.ui.body.form._click_done(None)

    def cancel(self):
        self.app.prev_screen()

    def done(self, mirror):
        log.debug("MirrorController.done next_screen mirror=%s", mirror)
        self.app.next_screen(self.endpoint.POST(MirrorPost(elected=mirror)))
