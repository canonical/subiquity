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
""" Module that deals with contract token selection. """

import asyncio
import logging
import time
from typing import Any, List

from subiquity.server.ubuntu_advantage import APIUsageError, UAInterface
from subiquitycore.async_helpers import schedule_task

log = logging.getLogger("subiquity.server.contract_selection")


class UPCSExpiredError(Exception):
    """Exception to be raised when a contract selection expired."""


class UnknownError(Exception):
    """Exception to be raised in case of unexpected error."""

    def __init__(self, message: str = "", errors: List[Any] = []) -> None:
        self.errors = errors
        super().__init__(message)


class ContractSelection:
    """Represents an already initiated contract selection."""

    def __init__(
        self,
        client: UAInterface,
        magic_token: str,
        user_code: str,
        validity_seconds: int,
    ) -> None:
        """Initialize the contract selection."""
        self.client = client
        self.magic_token = magic_token
        self.user_code = user_code
        self.validity_seconds = validity_seconds
        self.task = asyncio.create_task(self._run_polling())

    @classmethod
    async def initiate(cls, client: UAInterface) -> "ContractSelection":
        """Initiate a contract selection and return a ContractSelection
        request object."""
        answer = await client.strategy.magic_initiate_v1()

        if answer["result"] != "success":
            raise UnknownError(errors=answer["errors"])

        return cls(
            client=client,
            magic_token=answer["data"]["attributes"]["token"],
            validity_seconds=answer["data"]["attributes"]["expires_in"],
            user_code=answer["data"]["attributes"]["user_code"],
        )

    async def _run_polling(self) -> str:
        """Runs the polling and eventually return a contract token."""
        # Wait an initial 30 seconds before sending the first request, then
        # send requests at regular interval every 10 seconds.
        await asyncio.sleep(30 / self.client.strategy.scale_factor)

        start_time = time.monotonic()
        answer = await self.client.strategy.magic_wait_v1(magic_token=self.magic_token)

        call_duration = time.monotonic() - start_time

        if answer["result"] == "success":
            return answer["data"]["attributes"]["contract_token"]

        exception = UnknownError()
        for error in answer["errors"]:
            if (
                error["code"] == "magic-attach-token-error"
                and call_duration >= 60 / self.client.strategy.scale_factor
            ):
                # Assume it's a timeout if it lasted more than 1 minute.
                exception = UPCSExpiredError(error["title"])
            else:
                log.warning("magic_wait_v1: %s: %s", error["code"], error["title"])

        raise exception

    def cancel(self):
        """Cancel the polling task and asynchronously delete the associated
        resource."""
        self.task.cancel()

        async def delete_resource() -> None:
            """Release the resource on the server."""
            try:
                answer = await self.client.strategy.magic_revoke_v1(
                    magic_token=self.magic_token
                )

            except APIUsageError as e:
                log.warning("failed to revoke magic-token: %r", e)
            else:
                if answer["result"] != "success":
                    log.debug("successfully revoked magic-token")
                    return
                for error in answer["errors"]:
                    log.warning(
                        "magic_revoke_v1: %s: %s", error["code"], error["title"]
                    )

        schedule_task(delete_resource())
