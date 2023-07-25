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
""" This module defines utilities to interface with the ubuntu-advantage-tools
helper. """

import asyncio
import contextlib
import json
import logging
import os
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime as dt
from subprocess import CompletedProcess
from typing import List, Sequence, Tuple, Union

import yaml

from subiquity.common.types import UbuntuProService, UbuntuProSubscription
from subiquitycore import utils

log = logging.getLogger("subiquity.server.ubuntu_advantage")


class InvalidTokenError(Exception):
    """Exception to be raised when the supplied token is invalid."""

    def __init__(self, token: str, message: str = "") -> None:
        self.token = token
        self.message = message
        super().__init__(message)


class ExpiredTokenError(Exception):
    """Exception to be raised when the supplied token has expired."""

    def __init__(self, token: str, expires: str, message: str = "") -> None:
        self.token = token
        self.expires = expires
        self.message = message
        super().__init__(message)


class CheckSubscriptionError(Exception):
    """Exception to be raised when we are unable to fetch information about
    the Ubuntu Advantage subscription."""

    def __init__(self, token: str, message: str = "") -> None:
        self.token = token
        self.message = message
        super().__init__(message)


class APIUsageError(Exception):
    """Exception to raise when the API call does not return valid JSON."""


class UAInterfaceStrategy(ABC):
    """Strategy to query information about a UA subscription."""

    @abstractmethod
    async def query_info(self, token: str) -> dict:
        """Return information about the UA subscription based on the token
        provided."""


class MockedUAInterfaceStrategy(UAInterfaceStrategy):
    """Mocked version of the Ubuntu Advantage interface strategy. The info it
    returns is based on example files and appearance of the UA token."""

    def __init__(self, scale_factor: int = 1):
        self.scale_factor = scale_factor
        self._user_code_count = 0
        super().__init__()

    async def query_info(self, token: str) -> dict:
        """Return the subscription info associated with the supplied
        UA token. No actual query is done to the UA servers in this
        implementation. Instead, we create a response based on the following
        rules:
        * Empty tokens are considered invalid.
        * Tokens starting with "x" will be considered expired.
        * Tokens starting with "i" will be considered invalid.
        * Tokens starting with "f" will generate an internal error.
        """
        await asyncio.sleep(1 / self.scale_factor)

        if not token:
            raise InvalidTokenError(token)

        if token[0] == "x":
            path = "examples/uaclient-status-expired.json"
        elif token[0] == "i":
            raise InvalidTokenError(token)
        elif token[0] == "f":
            raise CheckSubscriptionError(token)
        else:
            path = "examples/uaclient-status-valid.json"

        with open(path, encoding="utf-8") as stream:
            return json.load(stream)

    def _next_user_code(self) -> str:
        """Return the next user code starting with AAAAAA."""
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ123456789"

        count = self._user_code_count
        self._user_code_count += 1

        user_code = ""
        # Generate a 6 characters code
        for i in range(6):
            user_code = alphabet[count % len(alphabet)] + user_code
            count //= len(alphabet)

        return user_code

    async def magic_initiate_v1(self) -> dict:
        """Simulate a success response from u.pro.attach.magic.initiate.v1
        endpoint."""
        await asyncio.sleep(1 / self.scale_factor)
        return {
            "data": {
                "attributes": {
                    "expires_in": 200,
                    "token": "123456789ABCDEF",
                    "user_code": self._next_user_code(),
                },
                "type": "MagicAttachInitiate",
            },
            "errors": [],
            "result": "success",
            "warnings": [],
        }

    async def magic_wait_v1(self, magic_token: str) -> dict:
        """Simulate a timeout respnose from u.pro.attach.magic.wait.v1
        endpoint."""
        # Simulate a normal timeout
        await asyncio.sleep(600 / self.scale_factor)
        return {
            "result": "failure",
            "errors": [
                {
                    "title": "The magic attach token is invalid, has "
                    " expired or never existed",
                    "code": "magic-attach-token-error",
                },
            ],
        }

    async def magic_revoke_v1(self, magic_token: str) -> dict:
        """Simulate a success respnose from u.pro.attach.magic.revoke.v1
        endpoint."""
        await asyncio.sleep(1 / self.scale_factor)
        return {
            "data": {
                "attributes": {},
                "type": "MagicAttachRevoke",
            },
            "errors": [],
            "result": "success",
            "warnings": [],
        }


class UAClientUAInterfaceStrategy(UAInterfaceStrategy):
    """Strategy that relies on UA client script to retrieve the information."""

    Executable = Union[str, Sequence[str]]
    scale_factor = 1

    def __init__(self, executable: Executable = "ubuntu-advantage") -> None:
        """Initialize the strategy using the path to the ubuntu-advantage
        executable we want to use. The executable can be specified as a
        sequence of strings so that we can specify the interpret to use as
        well.
        """
        self.executable: List[str] = (
            [executable] if isinstance(executable, str) else list(executable)
        )
        self.uaclient_config = None
        super().__init__()

    def load_default_uaclient_config(self) -> None:
        with open("/etc/ubuntu-advantage/uaclient.conf") as fh:
            self.uaclient_config = yaml.safe_load(fh)

    @contextlib.contextmanager
    def uaclient_config_file(self) -> str:
        """Yields a path to a file that contains the uaclient configuration."""
        try:
            if self.uaclient_config is None:
                yield "/etc/ubuntu-advantage/uaclient.conf"
            else:
                with tempfile.NamedTemporaryFile(mode="w") as fh:
                    yaml.dump(self.uaclient_config, fh)
                    yield fh.name
        finally:
            pass

    async def query_info(self, token: str) -> dict:
        """Return the subscription info associated with the supplied
        UA token. The information will be queried using the UA client
        executable passed to the initializer.
        """
        if not token:
            # u-a-c does not produce the expected output when the contract
            # token is empty ; so let's not call it at all.
            raise InvalidTokenError(token)

        command = tuple(self.executable) + (
            "status",
            "--format",
            "json",
            "--simulate-with-token",
            token,
        )

        with self.uaclient_config_file() as config_file:
            env = os.environ.copy()
            env["UA_CONFIG_FILE"] = config_file
            # On error, the command will exit with status 1. When that happens,
            # the output should still be formatted as a JSON object and we can
            # inspect it to know the reason of the failure. This is how we
            # figure out if the contract token was invalid.
            proc: CompletedProcess = await utils.arun_command(
                command, check=False, env=env
            )
        if proc.returncode == 0:
            # TODO check if we're not returning a string or a list
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError:
                log.exception("Failed to parse output of command %r", command)
        elif proc.returncode == 1:
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                log.exception("Failed to parse output of command %r", command)
            else:
                token_invalid = False
                with contextlib.suppress(KeyError):
                    for error in data["errors"]:
                        if error["message_code"] == "attach-invalid-token":
                            token_invalid = True
                        log.debug(
                            "error reported by u-a-c: %s: %s",
                            error["message_code"],
                            error["message"],
                        )
                if token_invalid:
                    raise InvalidTokenError(token)

        else:
            log.exception("Failed to execute command %r", command)

        message = "Unable to retrieve subscription information."
        raise CheckSubscriptionError(token, message=message)

    async def _api_call(self, endpoint: str, params: Sequence[Tuple[str, str]]) -> dict:
        command = list(tuple(self.executable)) + ["api", endpoint, "--args"]

        for key, value in params:
            command.append(f"{key}={value}")

        with self.uaclient_config_file() as config_file:
            env = os.environ.copy()
            env["UA_CONFIG_FILE"] = config_file
            proc: CompletedProcess = await utils.arun_command(
                tuple(command), check=False, env=env
            )
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            log.exception("Failed to parse output of command %r", command)
            raise APIUsageError

    async def magic_initiate_v1(self) -> dict:
        """Call the u.pro.attach.magic.initiate.v1 endpoint."""
        return await self._api_call(
            endpoint="u.pro.attach.magic.initiate.v1", params=[]
        )

    async def magic_wait_v1(self, magic_token: str) -> dict:
        """Call the u.pro.attach.magic.wait.v1 endpoint."""
        return await self._api_call(
            endpoint="u.pro.attach.magic.wait.v1", params=[("magic_token", magic_token)]
        )

    async def magic_revoke_v1(self, magic_token: str) -> dict:
        """Call the u.pro.attach.magic.revoke.v1 endpoint."""
        return await self._api_call(
            endpoint="u.pro.attach.magic.revoke.v1",
            params=[("magic_token", magic_token)],
        )


class UAInterface:
    """Interface to obtain Ubuntu Advantage subscription information."""

    def __init__(self, strategy: UAInterfaceStrategy):
        self.strategy = strategy

    async def get_subscription_status(self, token: str) -> dict:
        """Return a dictionary containing the subscription information."""
        return await self.strategy.query_info(token)

    async def get_subscription(self, token: str) -> UbuntuProSubscription:
        """Return the name of the contract, the name of the account and the
        list of activable services (i.e. services that are entitled to the
        subscription and available on the current hardware).
        """
        info = await self.get_subscription_status(token)

        # Sometimes, a time zone offset of 0 is replaced by the letter Z. This
        # is specified in RFC 3339 but not supported by fromisoformat.
        # See https://bugs.python.org/issue35829
        expiration = dt.fromisoformat(info["expires"].replace("Z", "+00:00"))
        if expiration.timestamp() <= dt.utcnow().timestamp():
            raise ExpiredTokenError(token, expires=info["expires"])

        def is_activable_service(service: dict) -> bool:
            # - the available field for a service refers to its availability on
            # the current machine (e.g. on Focal running on a amd64 CPU) ;
            # whereas
            # - the entitled field tells us if the contract covers the service.
            return service["available"] == "yes" and service["entitled"] == "yes"

        def service_from_dict(service: dict) -> UbuntuProService:
            return UbuntuProService(
                name=service["name"],
                description=service["description"],
                auto_enabled=service["auto_enabled"] == "yes",
            )

        activable_services: List[UbuntuProService] = []

        for service in info["services"]:
            if not is_activable_service(service):
                continue
            activable_services.append(service_from_dict(service))

        return UbuntuProSubscription(
            account_name=info["account"]["name"],
            contract_name=info["contract"]["name"],
            contract_token=token,
            services=activable_services,
        )
