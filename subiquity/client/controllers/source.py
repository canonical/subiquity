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

log = logging.getLogger('subiquity.client.controllers.source')


class SourceController(SubiquityTuiController):

    endpoint_name = 'source'

    async def make_ui(self):
        sources = await self.endpoint.GET()
        return SourceView(self, sources.sources, sources.current_id)

    def run_answers(self):
        if 'source' in self.answers:
            self.app.ui.body.form.source.value = self.answers['source']
            self.app.ui.body.form._click_done(None)

    def cancel(self):
        self.app.prev_screen()

    def done(self, source_id):
        log.debug("SourceController.done source_id=%s", source_id)
        self.app.next_screen(self.endpoint.POST(source_id))
