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

import logging
from typing import List

from subiquity.client.controller import (
    SubiquityTuiController,
    )
from subiquity.common.types import (
    SnapCheckState,
    SnapSelection,
    )
from subiquity.ui.views.snaplist import SnapListView

log = logging.getLogger('subiquity.client.controllers.snaplist')


class SnapListController(SubiquityTuiController):

    endpoint_name = 'snaplist'

    async def make_ui(self):
        data = await self.endpoint.GET()
        if data.status == SnapCheckState.FAILED:
            # If loading snaps failed or network is disabled, skip the screen.
            log.debug('snaplist GET failed, mark done')
            self.done([])
        return SnapListView(self, data)

    def run_answers(self):
        if 'snaps' in self.answers:
            selections = []
            for snap_name, selection in self.answers['snaps'].items():
                if 'is_classic' in selection:
                    selection['classic'] = selection.pop('is_classic')
                selections.append(SnapSelection(name=snap_name, **selection))
            self.done(selections)

    def done(self, selections: List[SnapSelection]):
        log.debug(
            "SnapListController.done next_screen snaps_to_install=%s",
            selections)
        self.app.next_screen(self.endpoint.POST(selections))

    def cancel(self, sender=None):
        self.app.prev_screen()

    async def get_list_wait(self):
        return await self.endpoint.GET(wait=True)

    async def get_snap_info(self, snap):
        if not snap.channels:
            data = await self.endpoint.snap_info.GET(snap_name=snap.name)
            snap.channels = data.channels
