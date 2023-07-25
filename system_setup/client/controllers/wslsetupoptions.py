# Copyright 2022 Canonical, Ltd.
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
from subiquity.common.types import WSLSetupOptions
from system_setup.ui.views.wslsetupoptions import WSLSetupOptionsView

log = logging.getLogger("system_setup.client.controllers.wslsetupoptions")


class WSLSetupOptionsController(SubiquityTuiController):
    endpoint_name = "wslsetupoptions"

    async def make_ui(self):
        data = await self.endpoint.GET()
        cur_lang = self.app.native_language

        return WSLSetupOptionsView(self, data, cur_lang)

    def run_answers(self):
        if all(elem in self.answers for elem in ["install_language_support_packages"]):
            configuration = WSLSetupOptions(**self.answers)
            self.done(configuration)

    def done(self, configuration_data):
        log.debug(
            "WSLSetupOptionsController.done next_screen user_spec=%s",
            configuration_data,
        )
        self.app.next_screen(self.endpoint.POST(configuration_data))

    def cancel(self):
        self.app.prev_screen()
