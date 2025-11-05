# Copyright 2024 Canonical, Ltd.
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

log = logging.getLogger("subiquity.server.controllers.homenode_token")

TOKEN_FILE = "/tmp/token"


class HomenodeTokenController(SubiquityController):
    endpoint = API.homenode_token

    autoinstall_key = "homenode-token"
    autoinstall_schema = {
        "type": ["string", "null"],
    }
    model_name = None  # No model needed, we just save to file

    def __init__(self, app):
        super().__init__(app)
        self.token = None

    def load_autoinstall_data(self, data):
        if data is not None:
            self.token = data
            self._save_token(data)

    def make_autoinstall(self):
        return self.token

    def serialize(self):
        return self.token

    def deserialize(self, data):
        self.token = data

    def _save_token(self, token):
        """Save the token to /tmp/token."""
        try:
            with open(TOKEN_FILE, "w") as f:
                f.write(token)
            log.info("Saved homenode token to %s", TOKEN_FILE)
        except Exception as e:
            log.error("Failed to save token to %s: %s", TOKEN_FILE, e)

    async def GET(self) -> str:
        return self.token or ""

    async def POST(self, data: str):
        self.token = data
        self._save_token(data)
        await self.configured()

