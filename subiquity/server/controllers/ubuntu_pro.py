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

import logging
import os

from subiquity.common.apidef import API
from subiquity.common.types import (
    UbuntuProInfo,
    UbuntuProCheckTokenAnswer,
    UbuntuProCheckTokenStatus,
)
from subiquity.server.ubuntu_advantage import (
    InvalidTokenError,
    ExpiredTokenError,
    CheckSubscriptionError,
    UAInterface,
    UAInterfaceStrategy,
    MockedUAInterfaceStrategy,
    UAClientUAInterfaceStrategy,
)
from subiquity.server.controller import SubiquityController

log = logging.getLogger("subiquity.server.controllers.ubuntu_pro")

TOKEN_DESC = """\
A valid token starts with a C and is followed by 23 to 29 Base58 characters.
See https://pkg.go.dev/github.com/btcsuite/btcutil/base58#CheckEncode"""


class UbuntuProController(SubiquityController):
    """ Represent the server-side Ubuntu Pro controller. """

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
        """ Initializer for server-side Ubuntu Pro controller. """
        strategy: UAInterfaceStrategy
        if app.opts.dry_run:
            strategy = MockedUAInterfaceStrategy(scale_factor=app.scale_factor)
        else:
            # Make sure we execute `$PYTHON "$SNAP/usr/bin/ubuntu-advantage"`.
            executable = (
                os.environ["PYTHON"],
                os.path.join(os.environ["SNAP"], "usr/bin/ubuntu-advantage"),
            )
            strategy = UAClientUAInterfaceStrategy(executable=executable)
        self.ua_interface = UAInterface(strategy)
        super().__init__(app)

    def load_autoinstall_data(self, data: dict) -> None:
        """ Load autoinstall data and update the model. """
        if data is None:
            return
        self.model.token = data.get("token", "")

    def make_autoinstall(self) -> dict:
        """ Return a dictionary that can be used as an autoinstall snippet for
        Ubuntu Pro.
        """
        if not self.model.token:
            return {}
        return {
            "token": self.model.token
        }

    def serialize(self) -> str:
        """ Save the current state of the model so it can be loaded later.
        Currently this function is called automatically by .configured().
        """
        return self.model.token

    def deserialize(self, token: str) -> None:
        """ Loads the last-known state of the model. """
        self.model.token = token

    async def GET(self) -> UbuntuProInfo:
        """ Handle a GET request coming from the client-side controller. """
        return UbuntuProInfo(token=self.model.token)

    async def POST(self, data: UbuntuProInfo) -> None:
        """ Handle a POST request coming from the client-side controller and
        then call .configured().
        """
        self.model.token = data.token
        await self.configured()

    async def skip_POST(self) -> None:
        """ When running on a non-LTS release, we want to call this so we can
        skip the screen on the client side. """
        await self.configured()

    async def check_token_GET(self, token: str) \
            -> UbuntuProCheckTokenAnswer:
        """ Handle a GET request asking whether the contract token is valid or
        not. If it is valid, we provide the list of activable services
        associated with the subscription.
        """
        services = None
        try:
            services = await \
                    self.ua_interface.get_activable_services(token=token)
        except InvalidTokenError:
            status = UbuntuProCheckTokenStatus.INVALID_TOKEN
        except ExpiredTokenError:
            status = UbuntuProCheckTokenStatus.EXPIRED_TOKEN
        except CheckSubscriptionError:
            status = UbuntuProCheckTokenStatus.UNKNOWN_ERROR
        else:
            status = UbuntuProCheckTokenStatus.VALID_TOKEN

        return UbuntuProCheckTokenAnswer(status=status, services=services)
