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

from subiquity.common.apidef import API
from subiquity.common.types import WSLConfigurationAdvanced
from subiquity.server.controller import SubiquityController
from subiquitycore.context import with_context
from system_setup.common.wsl_conf import default_loader
from system_setup.common.wsl_utils import convert_if_bool

log = logging.getLogger("system_setup.server.controllers.wslconfadvanced")


class WSLConfigurationAdvancedController(SubiquityController):
    endpoint = API.wslconfadvanced

    autoinstall_key = model_name = "wslconfadvanced"
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "interop_enabled": {"type": "boolean"},
            "interop_appendwindowspath": {"type": "boolean"},
            "automount_enabled": {"type": "boolean"},
            "automount_mountfstab": {"type": "boolean"},
            "systemd_enabled": {"type": "boolean"},
        },
        "additionalProperties": False,
    }

    def __init__(self, app):
        super().__init__(app)

        # load the config file
        root_dir = self.app.base_model.root
        data = default_loader(root_dir, is_advanced=True)

        if data:
            proc_data = {key: convert_if_bool(value) for (key, value) in data.items()}
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
            data.interop_enabled = self.model.wslconfadvanced.interop_enabled
            data.interop_appendwindowspath = (
                self.model.wslconfadvanced.interop_appendwindowspath
            )
            data.automount_enabled = self.model.wslconfadvanced.automount_enabled
            data.automount_mountfstab = self.model.wslconfadvanced.automount_mountfstab
            data.systemd_enabled = self.model.wslconfadvanced.systemd_enabled
        return data

    async def POST(self, data: WSLConfigurationAdvanced):
        self.model.apply_settings(data)
        await self.configured()
