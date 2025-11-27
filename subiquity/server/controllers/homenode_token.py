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
from subiquity.common.types import (
    HomenodeTokenCheckAnswer,
    HomenodeTokenCheckStatus,
    HomenodeTokenResponse,
)
from subiquity.server.akash_homenode import (
    AkashAPIInterface,
    CheckTokenError,
    ExpiredTokenError,
    HTTPAkashAPIStrategy,
    InvalidTokenError,
    MockedAkashAPIStrategy,
)
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
        # Initialize Akash API interface
        if app.opts.dry_run:
            strategy = MockedAkashAPIStrategy()
        else:
            strategy = HTTPAkashAPIStrategy()
        self.akash_api = AkashAPIInterface(strategy)

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
        """Save the installation key to /tmp/token."""
        try:
            with open(TOKEN_FILE, "w") as f:
                f.write(token)
            log.info("Saved homenode installation key to %s", TOKEN_FILE)
        except Exception as e:
            log.error("Failed to save installation key to %s: %s", TOKEN_FILE, e)

    async def GET(self) -> HomenodeTokenResponse:
        """Handle a GET request coming from the client-side controller."""
        has_network = self.app.base_model.network.has_network
        return HomenodeTokenResponse(token=self.token or "", has_network=has_network)

    async def POST(self, data: str) -> None:
        self.token = data
        self._save_token(data)
        await self.configured()

    async def check_token_GET(self, token: str) -> HomenodeTokenCheckAnswer:
        """Handle a GET request asking whether the installation key is valid.
        
        Returns:
            HomenodeTokenCheckAnswer with validation status
        """
        log.info("check_token_GET called with token: %s", token[:10] + "..." if len(token) > 10 else token)
        log.info("Network status: has_network=%s", self.app.base_model.network.has_network)
        
        # Check if network is available
        if not self.app.base_model.network.has_network:
            log.warning("Network not available, returning NO_NETWORK status")
            return HomenodeTokenCheckAnswer(
                status=HomenodeTokenCheckStatus.NO_NETWORK,
                message="Network is not available. Please configure network first."
            )

        try:
            # Verify installation key with Akash API
            log.info("Calling akash_api.verify_installation_key")
            result = await self.akash_api.verify_installation_key(token)
            log.info("Installation key validation successful: %s", token[:10] + "...")
            return HomenodeTokenCheckAnswer(
                status=HomenodeTokenCheckStatus.VALID_TOKEN,
                message=result.get("data", {}).get("message", "Installation key is valid")
            )
        except InvalidTokenError as e:
            log.warning("Invalid installation key: %s", e.message)
            return HomenodeTokenCheckAnswer(
                status=HomenodeTokenCheckStatus.INVALID_TOKEN,
                message=e.message or "Invalid installation key"
            )
        except ExpiredTokenError as e:
            log.warning("Expired installation key: %s", e.message)
            return HomenodeTokenCheckAnswer(
                status=HomenodeTokenCheckStatus.EXPIRED_TOKEN,
                message=e.message or "Installation key has expired"
            )
        except CheckTokenError as e:
            log.error("Installation key verification failed: %s", e.message)
            return HomenodeTokenCheckAnswer(
                status=HomenodeTokenCheckStatus.UNKNOWN_ERROR,
                message=e.message or "Failed to verify installation key"
            )
        except Exception as e:
            log.exception("Unexpected error during installation key verification")
            return HomenodeTokenCheckAnswer(
                status=HomenodeTokenCheckStatus.UNKNOWN_ERROR,
                message=f"Unexpected error: {str(e)}"
            )

