# Copyright 2015 Canonical, Ltd.
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
from subiquity.ui.views.welcome import WelcomeView

log = logging.getLogger('subiquity.client.controllers.welcome')


class WelcomeController(SubiquityTuiController):

    endpoint_name = 'locale'

    async def make_ui(self):
        language = await self.endpoint.GET()
        serial = self.app.opts.run_on_serial
        if serial:
            ips = await self.app.client.network.global_addresses.GET()
        else:
            ips = None
        return WelcomeView(self, language, serial, ips)

    def run_answers(self):
        if 'lang' in self.answers:
            self.done(self.answers['lang'])

    def done(self, code):
        log.debug("WelcomeController.done %s next_screen", code)
        self.signal.emit_signal('l10n:language-selected', code)
        self.app.next_screen(self.endpoint.POST(code))

    def cancel(self):
        # Can't go back from here!
        pass
