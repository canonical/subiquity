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
from subiquity.common.types import WSLConfigurationAdvanced
from system_setup.ui.views.wslconfadvanced import WSLConfigurationAdvancedView

log = logging.getLogger('system_setup.client.controllers.wslconfadvanced')


class WSLConfigurationAdvancedController(SubiquityTuiController):
    endpoint_name = 'wslconfadvanced'

    async def make_ui(self):
        data = await self.endpoint.GET()
        return WSLConfigurationAdvancedView(self, data)

    def run_answers(self):
        if all(elem in self.answers for elem in
               ['interop_enabled', 'interop_appendwindowspath',
                'gui_theme', 'gui_followwintheme', 'interop_guiintegration',
                'interop_audiointegration', 'interop_advancedipdetection',
                'motd_wslnewsenabled', 'automount_enabled',
                'automount_mountfstab']):

            reconfiguration = WSLConfigurationAdvanced(**self.answers)
            self.done(reconfiguration)

    def done(self, reconf_data):
        log.debug(
            "WSLConfigurationAdvancedController.done next_screen user_spec=%s",
            reconf_data)
        self.app.next_screen(self.endpoint.POST(reconf_data))

    def cancel(self):
        self.app.prev_screen()
