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

import attr

from subiquity.common.apidef import API
from subiquity.common.types import WSLSetupOptions
from subiquity.server.controller import SubiquityController
from subiquitycore.context import with_context

log = logging.getLogger("system_setup.server.controllers.wslsetupoptions")


class WSLSetupOptionsController(SubiquityController):
    endpoint = API.wslsetupoptions

    autoinstall_key = model_name = "wslsetupoptions"
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "install_language_support_packages": {"type": "boolean"},
        },
        "additionalProperties": False,
    }

    def load_autoinstall_data(self, data):
        if data is not None:
            identity_data = WSLSetupOptions(**data)
            self.model.apply_settings(identity_data)

    @with_context()
    async def apply_autoinstall_config(self, context=None):
        pass

    def make_autoinstall(self):
        r = attr.asdict(self.model.wslconfbase)
        return r

    async def GET(self) -> WSLSetupOptions:
        data = WSLSetupOptions()
        if self.model.wslsetupoptions is not None:
            data.install_language_support_packages = (
                self.model.wslsetupoptions.install_language_support_packages
            )
        return data

    async def POST(self, data: WSLSetupOptions):
        self.model.apply_settings(data)
        await self.configured()
