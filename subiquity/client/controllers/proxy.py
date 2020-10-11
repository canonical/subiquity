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
from subiquity.ui.views.proxy import ProxyView

log = logging.getLogger('subiquity.client.controllers.proxy')


class ProxyController(SubiquityTuiController):

    endpoint_name = 'proxy'

    async def make_ui(self):
        proxy = await self.endpoint.GET()
        return ProxyView(self, proxy)

    def run_answers(self):
        if 'proxy' in self.answers:
            self.done(self.answers['proxy'])

    def cancel(self):
        self.app.prev_screen()

    def done(self, proxy):
        log.debug("ProxyController.done next_screen proxy=%s", proxy)
        self.app.next_screen(self.endpoint.POST(proxy))
