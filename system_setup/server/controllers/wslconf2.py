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

import attr

from subiquitycore.context import with_context

from subiquity.common.apidef import API
from subiquity.common.types import WSLConfiguration2Data
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.wsl_integration_2')


class WSLConfiguration2Controller(SubiquityController):

    endpoint = API.wslconf2

    autoinstall_key = model_name = "wslconf2"
    autoinstall_schema = {
        'type': 'object',
        'properties': {
            'custom_path': {'type': 'string'},
            'custom_mount_opt': {'type': 'string'},
            'gen_host': {'type': 'boolean'},
            'gen_resolvconf': {'type': 'boolean'},
            'interop_enabled': {'type': 'boolean'},
            'interop_appendwindowspath': {'type': 'boolean'},
            'gui_theme': {'type': 'string'},
            'gui_followwintheme': {'type': 'boolean'},
            'legacy_gui': {'type': 'boolean'},
            'legacy_audio': {'type': 'boolean'},
            'adv_ip_detect': {'type': 'boolean'},
            'wsl_motd_news': {'type': 'boolean'},
            'automount': {'type': 'boolean'},
            'mountfstab': {'type': 'boolean'}
            },
        'required': [],
        'additionalProperties': False,
        }

    def load_autoinstall_data(self, data):
        if data is not None:
            identity_data = WSLConfiguration2Data(
                custom_path=data['custom_path'],
                custom_mount_opt=data['custom_mount_opt'],
                gen_host=data['gen_host'],
                gen_resolvconf=data['gen_resolvconf'],
                interop_enabled=data['interop_enabled'],
                interop_appendwindowspath=data['interop_appendwindowspath'],
                gui_theme=data['gui_theme'],
                gui_followwintheme=data['gui_followwintheme'],
                legacy_gui=data['legacy_gui'],
                legacy_audio=data['legacy_audio'],
                adv_ip_detect=data['adv_ip_detect'],
                wsl_motd_news=data['wsl_motd_news'],
                automount=data['automount'],
                mountfstab=data['mountfstab']
            )
            self.model.apply_settings(identity_data, self.opts.dry_run)

    @with_context()
    async def apply_autoinstall_config(self, context=None):
        pass

    def make_autoinstall(self):
        r = attr.asdict(self.model.wslconf2)
        return r

    async def GET(self) -> WSLConfiguration2Data:
        data = WSLConfiguration2Data()
        if self.model.wslconf2 is not None:
            data.custom_path = self.model.wslconf2.custom_path
            data.custom_mount_opt = self.model.wslconf2.custom_mount_opt
            data.gen_host = self.model.wslconf2.gen_host
            data.gen_resolvconf = self.model.wslconf2.gen_resolvconf
            data.interop_enabled = self.model.wslconf2.interop_enabled
            data.interop_appendwindowspath = self.model.wslconf2.interop_appendwindowspath
            data.gui_theme = self.model.wslconf2.gui_theme
            data.gui_followwintheme = self.model.wslconf2.gui_followwintheme
            data.legacy_gui = self.model.wslconf2.legacy_gui
            data.legacy_audio = self.model.wslconf2.legacy_audio
            data.adv_ip_detect = self.model.wslconf2.adv_ip_detect
            data.wsl_motd_news = self.model.wslconf2.wsl_motd_news
            data.automount = self.model.wslconf2.automount
            data.mountfstab = self.model.wslconf2.mountfstab
        return data

    async def POST(self, data: WSLConfiguration2Data):
        self.model.apply_settings(data, self.opts.dry_run)
        self.configured()
