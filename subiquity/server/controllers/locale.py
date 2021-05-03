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


log = logging.getLogger('subiquity.server.controllers.locale')


class LocaleController(SubiquityController):

    endpoint = API.locale

    autoinstall_key = model_name = "locale"
    autoinstall_schema = {'type': 'string'}
    autoinstall_default = 'en_US.UTF-8'

    def load_autoinstall_data(self, data):
        os.environ["LANG"] = data

    def start(self):
        self.model.selected_language = os.environ.get("LANG")
        self.configured()

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
        self.configured()
