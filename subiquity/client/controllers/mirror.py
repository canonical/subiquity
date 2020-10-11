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

from subiquity.client.controller import SubiquityTuiController
from subiquity.ui.views.mirror import MirrorView

log = logging.getLogger('subiquity.client.controllers.mirror')


class MirrorController(SubiquityTuiController):

    endpoint_name = 'mirror'

    async def make_ui(self):
        mirror = await self.endpoint.GET()
        return MirrorView(self, mirror)

    def run_answers(self):
        if 'mirror' in self.answers:
            self.done(self.answers['mirror'])
        elif 'country-code' in self.answers \
             or 'accept-default' in self.answers:
            self.app.ui.body.form._click_done(None)

    def cancel(self):
        self.app.prev_screen()

    def done(self, mirror):
        log.debug("MirrorController.done next_screen mirror=%s", mirror)
        self.app.next_screen(self.endpoint.POST(mirror))
