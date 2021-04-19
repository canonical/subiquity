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
from subiquity.ui.views.serial import SerialView
from subiquitycore.tuicontroller import Skip

log = logging.getLogger('subiquity.client.controllers.serial')


class SerialController(SubiquityTuiController):
    async def make_ui(self):
        if not self.app.opts.run_on_serial:
            raise Skip()
        ssh_info = await self.app.client.meta.ssh_info.GET()
        return SerialView(self, ssh_info)

    def done(self, rich):
        log.debug("SerialController.done rich %s next_screen", rich)
        self.app.set_rich(rich)
        self.app.next_screen()

    def cancel(self):
        # Can't go back from here!
        pass
