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
""" This module defines utilities to interface with Ubuntu Advantage
subscriptions. """

from abc import ABC, abstractmethod
from datetime import datetime as dt
import json
import logging
from subprocess import CalledProcessError, CompletedProcess
from typing import List, Sequence, Union
import asyncio

from subiquitycore import utils


log = logging.getLogger("subiquitycore.common.ubuntu_advantage")


class InvalidUATokenError(Exception):
    """ Exception to be raised when the supplied token is invalid. """
    def __init__(self, token: str, message: str = "") -> None:
        self.token = token
        self.message = message
        super().__init__(message)


class ExpiredUATokenError(Exception):
    """ Exception to be raised when the supplied token has expired. """
    def __init__(self, token: str, expires: str, message: str = "") -> None:
        self.token = token
        self.expires = expires
        self.message = message
        super().__init__(message)


class CheckSubscriptionError(Exception):
    """ Exception to be raised when we are unable to fetch information about
    the Ubuntu Advantage subscription. """
    def __init__(self, token: str, message: str = "") -> None:
        self.token = token
        self.message = message
        super().__init__(message)


class UAInterfaceStrategy(ABC):
    """ Strategy to query information about a UA subscription. """
    @abstractmethod
    async def query_info(self, token: str) -> dict:
        """ Return information about the UA subscription based on the token
        provided.  """


class MockedUAInterfaceStrategy(UAInterfaceStrategy):
    """ Mocked version of the Ubuntu Advantage interface strategy. The info it
    returns is based on example files and appearance of the UA token. """
    def __init__(self, scale_factor: int = 1):
        self.scale_factor = scale_factor
        super().__init__()

    async def query_info(self, token: str) -> dict:
        """ Return the subscription info associated with the supplied
        UA token. No actual query is done to the UA servers in this
        implementation. Instead, we create a response based on the following
        rules:
        * Tokens starting with "x" will be considered expired.
        * Tokens starting with "i" will be considered invalid.
        * Tokens starting with "f" will generate an internal error.
        """
        await asyncio.sleep(1 / self.scale_factor)

        if token[0] == "x":
            path = "examples/uaclient-status-expired.json"
        elif token[0] == "i":
            raise InvalidUATokenError(token)
        elif token[0] == "f":
            raise CheckSubscriptionError(token)
        else:
            path = "examples/uaclient-status-valid.json"

        with open(path, encoding="utf-8") as stream:
            return json.load(stream)


class UAClientUAInterfaceStrategy(UAInterfaceStrategy):
    """ Strategy that relies on UA client script to retrieve the information.
    """
    Executable = Union[str, Sequence[str]]

    def __init__(self, executable: Executable = "ubuntu-advantage") -> None:
        """ Initialize the strategy using the path to the ubuntu-advantage
        executable we want to use. The executable can be specified as a
        sequence of strings so that we can specify the interpret to use as
        well.
        """
        self.executable: List[str] = \
            [executable] if isinstance(executable, str) else list(executable)
        super().__init__()

    async def query_info(self, token: str) -> dict:
        """ Return the subscription info associated with the supplied
        UA token. The information will be queried using the UA client
        executable passed to the initializer.
        """
        command = tuple(self.executable) + (
            "status",
            "--format", "json",
            "--simulate-with-token", token,
        )
        try:
            proc: CompletedProcess = await utils.arun_command(command,
                                                              check=True)
            # TODO check if we're not returning a string or a list
            return json.loads(proc.stdout)
        except CalledProcessError:
            log.exception("Failed to execute command %r", command)
            # TODO Check if the command failed because the token is invalid.
            # Currently, ubuntu-advantage fails with the following error when
            # the token is invalid:
            # * Failed to connect to authentication server
            # * Check your Internet connection and try again.
        except json.JSONDecodeError:
            log.exception("Failed to parse output of command %r", command)

        message = "Unable to retrieve subscription information."
        raise CheckSubscriptionError(token, message=message)


class UAInterface:
    """ Interface to obtain Ubuntu Advantage subscription information. """
    def __init__(self, strategy: UAInterfaceStrategy):
        self.strategy = strategy

    async def get_subscription(self, token: str) -> dict:
        """ Return a dictionary containing the subscription information. """
        return await self.strategy.query_info(token)

    async def get_activable_services(self, token: str) -> List[dict]:
        """ Return a list of activable services (i.e. services that are
        entitled to the subscription and available on the current hardware).
        """
        info = await self.get_subscription(token)

        expiration = dt.fromisoformat(info["expires"])
        if expiration.timestamp() <= dt.utcnow().timestamp():
            raise ExpiredUATokenError(token, expires=info["expires"])

        def is_activable_service(service: dict) -> bool:
            # - the available field for a service refers to its availability on
            # the current machine (e.g. on Focal running on a amd64 CPU) ;
            # whereas
            # - the entitled field tells us if the contract covers the service.
            return service["available"] == "yes" \
               and service["entitled"] == "yes"

        return [svc for svc in info["services"] if is_activable_service(svc)]
