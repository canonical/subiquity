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

from subiquity.common.apidef import API
from subiquity.common.types import CodecsData
from subiquity.server.controller import SubiquityController

log = logging.getLogger("subiquity.server.controllers.codecs")


class CodecsController(SubiquityController):
    endpoint = API.codecs

    autoinstall_key = model_name = "codecs"
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "install": {
                "type": "boolean",
            },
        },
    }
    autoinstall_default = {"install": False}

    def serialize(self):
        return self.model.do_install

    def deserialize(self, data):
        if data is None:
            return
        self.model.do_install = data

    def make_autoinstall(self):
        return {
            "install": self.model.do_install,
        }

    def load_autoinstall_data(self, data):
        if data is not None and "install" in data:
            self.model.do_install = data["install"]

    async def GET(self) -> CodecsData:
        return CodecsData(install=self.model.do_install)

    async def POST(self, data: CodecsData) -> None:
        self.model.do_install = data.install
        await self.configured()
