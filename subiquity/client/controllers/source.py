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

from subiquity.client.controller import SubiquityTuiController
from subiquity.ui.views.source import SourceView

log = logging.getLogger("subiquity.client.controllers.source")


class SourceController(SubiquityTuiController):
    endpoint_name = "source"

    async def make_ui(self):
        sources = await self.endpoint.GET()
        return SourceView(
            self, sources.sources, sources.current_id, sources.search_drivers
        )

    def run_answers(self):
        form = self.app.ui.body.form
        if "search_drivers" in self.answers:
            form.search_drivers.value = self.answers["search_drivers"]
        if "source" in self.answers:
            wanted_id = self.answers["source"]
            for bf in form._fields:
                if bf is form.search_drivers:
                    continue
                bf.value = bf.field.name == wanted_id
            form._click_done(None)

    def cancel(self):
        self.app.prev_screen()

    def done(self, source_id, search_drivers: bool):
        log.debug(
            "SourceController.done source_id=%s, search_drivers=%s",
            source_id,
            search_drivers,
        )
        self.app.next_screen(self.endpoint.POST(source_id, search_drivers))
