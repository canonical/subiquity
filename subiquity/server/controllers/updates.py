# Copyright 2018 Canonical, Ltd.
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

from subiquity.common.apidef import API
from subiquity.server.controller import SubiquityController


log = logging.getLogger('subiquity.server.controllers.updates')


class UpdatesController(SubiquityController):

    endpoint = API.updates

    autoinstall_key = model_name = "updates"
    autoinstall_schema = {
        'type': 'string',
        'enum': ['security', 'all'],
    }
    autoinstall_default = 'security'

    def __init__(self, app):
        super().__init__(app)

    def load_autoinstall_data(self, data):
        if data is None:
            return
        self.model.updates = data

    def make_autoinstall(self):
        return self.model.updates

    def serialize(self):
        return self.model.updates

    def deserialize(self, data):
        self.model.updates = data

    async def GET(self) -> str:
        return self.model.updates

    async def POST(self, data: str):
        self.model.updates = data
        self.configured()
