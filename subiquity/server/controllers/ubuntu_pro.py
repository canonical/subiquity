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
""" Module defining the server-side controller class for Ubuntu Advantage. """

import asyncio
import logging
import os
from typing import Optional

from subiquity.common.apidef import API
from subiquity.common.types import (
    UbuntuProCheckTokenAnswer,
    UbuntuProCheckTokenStatus,
    UbuntuProInfo,
    UbuntuProResponse,
    UPCSInitiateResponse,
    UPCSWaitResponse,
    UPCSWaitStatus,
)
from subiquity.server.contract_selection import ContractSelection, UPCSExpiredError
from subiquity.server.controller import SubiquityController
from subiquity.server.ubuntu_advantage import (
    CheckSubscriptionError,
    ExpiredTokenError,
    InvalidTokenError,
    MockedUAInterfaceStrategy,
    UAClientUAInterfaceStrategy,
    UAInterface,
    UAInterfaceStrategy,
)

log = logging.getLogger("subiquity.server.controllers.ubuntu_pro")

TOKEN_DESC = """\
A valid token starts with a C and is followed by 23 to 29 Base58 characters.
See https://pkg.go.dev/github.com/btcsuite/btcutil/base58#CheckEncode"""


class UPCSAlreadyInitiatedError(Exception):
    """Exception to be raised when trying to initiate a contract selection
    while another contract selection is already pending."""


class UPCSCancelledError(Exception):
    """Exception to be raised when a contract selection got cancelled."""


class UPCSNotInitiatedError(Exception):
    """Exception to be raised when trying to cancel or wait on a contract
    selection that was not initiated."""


class UbuntuProController(SubiquityController):
    """Represent the server-side Ubuntu Pro controller."""

    endpoint = API.ubuntu_pro

    model_name = "ubuntu_pro"
    autoinstall_key = "ubuntu-pro"
    autoinstall_key_alias = "ubuntu-advantage"
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "token": {
                "type": "string",
                "minLength": 24,
                "maxLength": 30,
                "pattern": "^C[1-9A-HJ-NP-Za-km-z]+$",
                "description": TOKEN_DESC,
            },
        },
    }

    def __init__(self, app) -> None:
        """Initializer for server-side Ubuntu Pro controller."""
        strategy: UAInterfaceStrategy
        if app.opts.dry_run:
            contracts_url = app.dr_cfg.pro_ua_contracts_url
            if app.dr_cfg.pro_magic_attach_run_locally:
                executable = "/usr/bin/ubuntu-advantage"
                strategy = UAClientUAInterfaceStrategy(executable=executable)
                strategy.load_default_uaclient_config()
                strategy.uaclient_config["contract_url"] = contracts_url
            else:
                strategy = MockedUAInterfaceStrategy(scale_factor=app.scale_factor)
        else:
            # Make sure we execute `$PYTHON "$SNAP/usr/bin/ubuntu-advantage"`.
            executable = (
                os.environ["PYTHON"],
                os.path.join(os.environ["SNAP"], "usr/bin/ubuntu-advantage"),
            )
            strategy = UAClientUAInterfaceStrategy(executable=executable)
        self.ua_interface = UAInterface(strategy)
        self.cs: Optional[ContractSelection] = None
        self.magic_token = Optional[str]
        super().__init__(app)

    def load_autoinstall_data(self, data: dict) -> None:
        """Load autoinstall data and update the model."""
        if data is None:
            return
        self.model.token = data.get("token", "")

    def make_autoinstall(self) -> dict:
        """Return a dictionary that can be used as an autoinstall snippet for
        Ubuntu Pro.
        """
        if not self.model.token:
            return {}
        return {"token": self.model.token}

    def serialize(self) -> str:
        """Save the current state of the model so it can be loaded later.
        Currently this function is called automatically by .configured().
        """
        return self.model.token

    def deserialize(self, token: str) -> None:
        """Loads the last-known state of the model."""
        self.model.token = token

    async def GET(self) -> UbuntuProResponse:
        """Handle a GET request coming from the client-side controller."""
        has_network = self.app.base_model.network.has_network
        return UbuntuProResponse(token=self.model.token, has_network=has_network)

    async def POST(self, data: UbuntuProInfo) -> None:
        """Handle a POST request coming from the client-side controller and
        then call .configured().
        """
        self.model.token = data.token
        await self.configured()

    async def skip_POST(self) -> None:
        """When running on a non-LTS release, we want to call this so we can
        skip the screen on the client side."""
        await self.configured()

    async def check_token_GET(self, token: str) -> UbuntuProCheckTokenAnswer:
        """Handle a GET request asking whether the contract token is valid or
        not. If it is valid, we provide the information about the subscription.
        """
        subscription = None
        try:
            subscription = await self.ua_interface.get_subscription(token=token)
        except InvalidTokenError:
            status = UbuntuProCheckTokenStatus.INVALID_TOKEN
        except ExpiredTokenError:
            status = UbuntuProCheckTokenStatus.EXPIRED_TOKEN
        except CheckSubscriptionError:
            status = UbuntuProCheckTokenStatus.UNKNOWN_ERROR
        else:
            status = UbuntuProCheckTokenStatus.VALID_TOKEN

        return UbuntuProCheckTokenAnswer(status=status, subscription=subscription)

    async def contract_selection_initiate_POST(self) -> UPCSInitiateResponse:
        """Initiate the contract selection request and start the polling."""
        if self.cs and not self.cs.task.done():
            raise UPCSAlreadyInitiatedError

        self.cs = await ContractSelection.initiate(client=self.ua_interface)

        return UPCSInitiateResponse(
            user_code=self.cs.user_code, validity_seconds=self.cs.validity_seconds
        )

    async def contract_selection_wait_GET(self) -> UPCSWaitResponse:
        """Block until the contract selection finishes or times out.
        If the contract selection is successful, the contract token is included
        in the response."""
        if self.cs is None:
            raise UPCSNotInitiatedError

        try:
            return UPCSWaitResponse(
                status=UPCSWaitStatus.SUCCESS,
                contract_token=await asyncio.shield(self.cs.task),
            )
        except UPCSExpiredError:
            return UPCSWaitResponse(status=UPCSWaitStatus.TIMEOUT, contract_token=None)

    async def contract_selection_cancel_POST(self) -> None:
        """Cancel the currently ongoing contract selection."""
        if self.cs is None:
            raise UPCSNotInitiatedError

        self.cs.cancel()
        self.cs = None
