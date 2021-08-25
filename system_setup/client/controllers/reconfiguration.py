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
from subiquity.common.types import WSLConfiguration2Data
from system_setup.ui.views.reconfiguration import ReconfigurationView

log = logging.getLogger('system_setup.client.controllers.reconfiguration')


class ReconfigurationController(SubiquityTuiController):
    endpoint_name = 'wslconf2'

    async def make_ui(self):
        data = await self.endpoint.GET()
        return ReconfigurationView(self, data)

    def run_answers(self):
        if all(elem in self.answers for elem in
               ['custom_path', 'custom_mount_opt', 'gen_host',
                'gen_resolvconf', 'interop_enabled',
                'interop_appendwindowspath', 'gui_theme',
                'gui_followwintheme', 'legacy_gui',
                'legacy_audio', 'adv_ip_detect',
                'wsl_motd_news', 'automount', 'mountfstab']):
            reconfiguration = WSLConfiguration2Data(
                custom_path=self.answers['custom_path'],
                custom_mount_opt=self.answers['custom_mount_opt'],
                gen_host=self.answers['gen_host'],
                gen_resolvconf=self.answers['gen_resolvconf'],
                interop_enabled=self.answers['interop_enabled'],
                interop_appendwindowspath=self
                .answers['interop_appendwindowspath'],
                gui_theme=self.answers['gui_theme'],
                gui_followwintheme=self.answers['gui_followwintheme'],
                legacy_gui=self.answers['legacy_gui'],
                legacy_audio=self.answers['legacy_audio'],
                adv_ip_detect=self.answers['adv_ip_detect'],
                wsl_motd_news=self.answers['wsl_motd_news'],
                automount=self.answers['automount'],
                mountfstab=self.answers['mountfstab']
            )
            self.done(reconfiguration)

    def done(self, reconf_data):
        log.debug(
            "ConfigurationController.done next_screen user_spec=%s",
            reconf_data)
        self.app.next_screen(self.endpoint.POST(reconf_data))

    def cancel(self):
        self.app.prev_screen()
