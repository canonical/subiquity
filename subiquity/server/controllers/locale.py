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
import os

from subiquity.common.apidef import API
from subiquity.server.controller import SubiquityController
from subiquity.server.types import InstallerChannels


log = logging.getLogger('subiquity.server.controllers.locale')


class LocaleController(SubiquityController):

    endpoint = API.locale

    autoinstall_key = model_name = "locale"
    autoinstall_schema = {'type': 'string'}
    autoinstall_default = 'en_US.UTF-8'

    def load_autoinstall_data(self, data):
        os.environ["LANG"] = data

    def start(self):
        # Language may have been initialized before start() is called.
        if self.model.selected_language == None:
            self.model.selected_language = os.environ.get("LANG") \
                    or self.autoinstall_default
        self.app.aio_loop.create_task(self.configured())
        self.app.hub.subscribe(
            (InstallerChannels.CONFIGURED, 'source'), self._set_source)

    def _set_source(self):
        current = self.app.base_model.source.current
        self.model.locale_support = current.locale_support

    def serialize(self):
        return self.model.selected_language

    def deserialize(self, data):
        self.model.switch_language(data)

    def make_autoinstall(self):
        return self.model.selected_language

    async def GET(self) -> str:
        return self.model.selected_language

    async def POST(self, data: str):
        self.model.switch_language(data)
        await self.configured()
