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
from subiquity.common.types import WSLConfigurationAdvanced
from subiquity.server.controller import SubiquityController

from system_setup.common.wsl_conf import default_loader
from system_setup.common.wsl_utils import convert_if_bool

log = logging.getLogger('system_setup.server.controllers.wslconfadvanced')


class WSLConfigurationAdvancedController(SubiquityController):

    endpoint = API.wslconfadvanced

    autoinstall_key = model_name = "wslconfadvanced"
    autoinstall_schema = {
        'type': 'object',
        'properties': {
            'interop_enabled': {'type': 'boolean'},
            'interop_appendwindowspath': {'type': 'boolean'},
            'gui_theme': {'type': 'string'},
            'gui_followwintheme': {'type': 'boolean'},
            'interop_guiintegration': {'type': 'boolean'},
            'interop_audiointegration': {'type': 'boolean'},
            'interop_advancedipdetection': {'type': 'boolean'},
            'motd_wslnewsenabled': {'type': 'boolean'},
            'automount_enabled': {'type': 'boolean'},
            'automount_mountfstab': {'type': 'boolean'}
        },
        'additionalProperties': False,
    }

    def __init__(self, app):
        super().__init__(app)

        # load the config file
        data = default_loader(is_advanced=True)

        if data:
            proc_data = \
                {key: convert_if_bool(value) for (key, value) in data.items()}
            reconf_data = WSLConfigurationAdvanced(**proc_data)
            self.model.apply_settings(reconf_data)

    def load_autoinstall_data(self, data):
        if data is not None:
            reconf_data = WSLConfigurationAdvanced(**data)
            self.model.apply_settings(reconf_data)

    @with_context()
    async def apply_autoinstall_config(self, context=None):
        pass

    def make_autoinstall(self):
        r = attr.asdict(self.model.wslconfadvanced)
        return r

    async def GET(self) -> WSLConfigurationAdvanced:
        data = WSLConfigurationAdvanced()
        if self.model.wslconfadvanced is not None:
            data.interop_enabled = \
                self.model.wslconfadvanced.interop_enabled
            data.interop_appendwindowspath = \
                self.model.wslconfadvanced.interop_appendwindowspath
            data.gui_theme = \
                self.model.wslconfadvanced.gui_theme
            data.gui_followwintheme = \
                self.model.wslconfadvanced.gui_followwintheme
            data.interop_guiintegration = \
                self.model.wslconfadvanced.interop_guiintegration
            data.interop_audiointegration = \
                self.model.wslconfadvanced.interop_audiointegration
            data.interop_advancedipdetection = \
                self.model.wslconfadvanced.interop_advancedipdetection
            data.motd_wslnewsenabled = \
                self.model.wslconfadvanced.motd_wslnewsenabled
            data.automount_enabled = \
                self.model.wslconfadvanced.automount_enabled
            data.automount_mountfstab = \
                self.model.wslconfadvanced.automount_mountfstab
        return data

    async def POST(self, data: WSLConfigurationAdvanced):
        self.model.apply_settings(data)
        await self.configured()
