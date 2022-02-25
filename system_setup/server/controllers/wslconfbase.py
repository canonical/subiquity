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
from subiquity.common.types import WSLConfigurationBase
from subiquity.server.controller import SubiquityController

from system_setup.common.wsl_conf import default_loader
from system_setup.common.wsl_utils import convert_if_bool

log = logging.getLogger('system_setup.server.controllers.wslconfbase')


class WSLConfigurationBaseController(SubiquityController):

    endpoint = API.wslconfbase

    autoinstall_key = model_name = "wslconfbase"
    autoinstall_schema = {
        'type': 'object',
        'properties': {
            'automount_root': {'type': 'string'},
            'automount_options': {'type': 'string'},
            'network_generatehosts': {'type': 'boolean'},
            'network_generateresolvconf': {'type': 'boolean'},
            },
        'additionalProperties': False,
        }

    def __init__(self, app):
        super().__init__(app)

        # load the config file
        data = default_loader()

        if data:
            proc_data = \
                {key: convert_if_bool(value) for (key, value) in data.items()}
            conf_data = WSLConfigurationBase(**proc_data)
            self.model.apply_settings(conf_data)

    def load_autoinstall_data(self, data):
        if data is not None:
            identity_data = WSLConfigurationBase(**data)
            self.model.apply_settings(identity_data)

    @with_context()
    async def apply_autoinstall_config(self, context=None):
        pass

    def make_autoinstall(self):
        r = attr.asdict(self.model.wslconfbase)
        return r

    async def GET(self) -> WSLConfigurationBase:
        data = WSLConfigurationBase()
        if self.model.wslconfbase is not None:
            data.automount_root = self.model.wslconfbase.automount_root
            data.automount_options = self.model.wslconfbase.automount_options
            data.network_generatehosts = \
                self.model.wslconfbase.network_generatehosts
            data.network_generateresolvconf = \
                self.model.wslconfbase.network_generateresolvconf
        return data

    async def POST(self, data: WSLConfigurationBase):
        self.model.apply_settings(data)
        await self.configured()
