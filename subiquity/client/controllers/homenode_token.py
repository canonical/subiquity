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

import asyncio
import logging
from typing import Callable, Optional

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.types import HomenodeTokenCheckStatus as TokenStatus
from subiquity.ui.views.homenode_token import HomenodeTokenView
from subiquitycore.async_helpers import schedule_task

log = logging.getLogger("subiquity.client.controllers.homenode_token")


class HomenodeTokenController(SubiquityTuiController):
    endpoint_name = "homenode_token"

    def __init__(self, app):
        """Initializer for the client-side HomenodeToken controller."""
        self._check_task: Optional[asyncio.Future] = None
        super().__init__(app)

    async def make_ui(self):
        homenode_info = await self.endpoint.GET()
        return HomenodeTokenView(
            self, token=homenode_info.token, has_network=homenode_info.has_network
        )

    def cancel(self):
        self.app.request_prev_screen()

    def done(self, token):
        log.debug("HomenodeTokenController.done next_screen installation_key=%s", token)
        self.app.request_next_screen(self.endpoint.POST(token))

    def check_token(
        self,
        token: str,
        on_success: Callable[[], None],
        on_failure: Callable[[TokenStatus, Optional[str]], None],
    ) -> None:
        """Asynchronously check the installation key via remote API."""
        log.info("HomenodeTokenController.check_token called for token: %s", token[:10] + "..." if len(token) > 10 else token)

        async def inner() -> None:
            try:
                log.info("Making API call to check_token endpoint")
                answer = await self.endpoint.check_token.GET(token)
                log.info("API response: status=%s, message=%s", answer.status, answer.message)
                if answer.status == TokenStatus.VALID_TOKEN:
                    log.info("Token is valid, calling on_success")
                    on_success()
                else:
                    log.warning("Token validation failed, calling on_failure")
                    on_failure(answer.status, answer.message)
            except Exception as e:
                log.exception("Exception during token check: %s", e)
                on_failure(TokenStatus.UNKNOWN_ERROR, str(e))

        self._check_task = schedule_task(inner())

    def cancel_check_token(self) -> None:
        """Cancel the asynchronous installation key check (if started)."""
        if self._check_task is not None:
            self._check_task.cancel()
            self._check_task = None

