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

import unittest
from subprocess import CompletedProcess
from unittest.mock import ANY, AsyncMock, patch

from subiquity.common.types import UbuntuProService
from subiquity.server.ubuntu_advantage import (
    CheckSubscriptionError,
    ExpiredTokenError,
    InvalidTokenError,
    MockedUAInterfaceStrategy,
    UAClientUAInterfaceStrategy,
    UAInterface,
)


class TestMockedUAInterfaceStrategy(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.strategy = MockedUAInterfaceStrategy(scale_factor=1_000_000)

    async def test_query_info_invalid(self):
        # Tokens starting with "i" in dry-run mode cause the token to be
        # reported as invalid.
        with self.assertRaises(InvalidTokenError):
            await self.strategy.query_info(token="invalidToken")

    async def test_query_info_failure(self):
        # Tokens starting with "f" in dry-run mode simulate an "internal"
        # error.
        with self.assertRaises(CheckSubscriptionError):
            await self.strategy.query_info(token="failure")

    async def test_query_info_expired(self):
        # Tokens starting with "x" is dry-run mode simulate an expired token.
        info = await self.strategy.query_info(token="xpiredToken")
        self.assertEqual(info["expires"], "2010-12-31T00:00:00+00:00")

    async def test_query_info_valid(self):
        # Other tokens are considered valid in dry-run mode.
        info = await self.strategy.query_info(token="validToken")
        self.assertEqual(info["expires"], "2035-12-31T00:00:00+00:00")


class TestUAClientUAInterfaceStrategy(unittest.IsolatedAsyncioTestCase):
    arun_command_sym = "subiquity.server.ubuntu_advantage.utils.arun_command"

    def test_init(self):
        # Default initializer.
        strategy = UAClientUAInterfaceStrategy()
        self.assertEqual(strategy.executable, ["ubuntu-advantage"])

        # Initialize with a mere path.
        strategy = UAClientUAInterfaceStrategy("/usr/bin/ubuntu-advantage")
        self.assertEqual(strategy.executable, ["/usr/bin/ubuntu-advantage"])

        # Initialize with a path + interpreter.
        strategy = UAClientUAInterfaceStrategy(("python3", "/usr/bin/ubuntu-advantage"))
        self.assertEqual(strategy.executable, ["python3", "/usr/bin/ubuntu-advantage"])

    async def test_query_info_succeeded(self):
        strategy = UAClientUAInterfaceStrategy()
        command = (
            "ubuntu-advantage",
            "status",
            "--format",
            "json",
            "--simulate-with-token",
            "123456789",
        )

        with patch(self.arun_command_sym) as mock_arun:
            mock_arun.return_value = CompletedProcess([], 0)
            mock_arun.return_value.stdout = "{}"
            await strategy.query_info(token="123456789")
            mock_arun.assert_called_once_with(command, check=False, env=ANY)

    async def test_query_info_unknown_error(self):
        strategy = UAClientUAInterfaceStrategy()
        command = (
            "ubuntu-advantage",
            "status",
            "--format",
            "json",
            "--simulate-with-token",
            "123456789",
        )

        with patch(self.arun_command_sym) as mock_arun:
            mock_arun.return_value.returncode = 2
            mock_arun.return_value.stdout = "{}"
            with self.assertRaises(CheckSubscriptionError):
                await strategy.query_info(token="123456789")
            mock_arun.assert_called_once_with(command, check=False, env=ANY)

    async def test_query_info_invalid_token(self):
        strategy = UAClientUAInterfaceStrategy()
        command = (
            "ubuntu-advantage",
            "status",
            "--format",
            "json",
            "--simulate-with-token",
            "123456789",
        )

        with patch(self.arun_command_sym) as mock_arun:
            mock_arun.return_value.returncode = 1
            mock_arun.return_value.stdout = """\
{
  "environment_vars": [],
  "errors": [
    {
      "message": "Invalid token. See https://ubuntu.com/advantage",
      "message_code": "attach-invalid-token",
      "service": null,
      "type": "system"
    }
  ],
  "result": "failure",
  "services": [],
  "warnings": []
}
"""
            with self.assertRaises(InvalidTokenError):
                await strategy.query_info(token="123456789")
            mock_arun.assert_called_once_with(command, check=False, env=ANY)

    async def test_query_info_invalid_json(self):
        strategy = UAClientUAInterfaceStrategy()
        command = (
            "ubuntu-advantage",
            "status",
            "--format",
            "json",
            "--simulate-with-token",
            "123456789",
        )

        with patch(self.arun_command_sym) as mock_arun:
            mock_arun.return_value = CompletedProcess([], 0)
            mock_arun.return_value.stdout = "invalid-json"
            with self.assertRaises(CheckSubscriptionError):
                await strategy.query_info(token="123456789")
            mock_arun.assert_called_once_with(command, check=False, env=ANY)

    async def test_api_call(self):
        strategy = UAClientUAInterfaceStrategy()
        with patch(self.arun_command_sym) as mock_arun:
            mock_arun.return_value = CompletedProcess([], 0)
            mock_arun.return_value.stdout = '{"result": "success"}'
            result = await strategy._api_call(
                endpoint="u.pro.attach.magic.wait.v1",
                params=[("magic_token", "132456")],
            )
            self.assertEqual(result, {"result": "success"})

        command = (
            "ubuntu-advantage",
            "api",
            "u.pro.attach.magic.wait.v1",
            "--args",
            "magic_token=132456",
        )
        mock_arun.assert_called_once_with(command, check=False, env=ANY)

    async def test_magic_initiate_v1(self):
        strategy = UAClientUAInterfaceStrategy()
        with patch.object(strategy, "_api_call", return_value={}) as api_call:
            await strategy.magic_initiate_v1()

        api_call.assert_called_once_with(
            endpoint="u.pro.attach.magic.initiate.v1", params=[]
        )

    async def test_magic_wait_v1(self):
        strategy = UAClientUAInterfaceStrategy()
        with patch.object(strategy, "_api_call", return_value={}) as api_call:
            await strategy.magic_wait_v1(magic_token="ABCDEF")

        api_call.assert_called_once_with(
            endpoint="u.pro.attach.magic.wait.v1", params=[("magic_token", "ABCDEF")]
        )

    async def test_magic_revoke_v1(self):
        strategy = UAClientUAInterfaceStrategy()
        with patch.object(strategy, "_api_call", return_value={}) as api_call:
            await strategy.magic_revoke_v1(magic_token="ABCDEF")

        api_call.assert_called_once_with(
            endpoint="u.pro.attach.magic.revoke.v1", params=[("magic_token", "ABCDEF")]
        )


class TestUAInterface(unittest.IsolatedAsyncioTestCase):
    async def test_mocked_get_subscription(self):
        strategy = MockedUAInterfaceStrategy(scale_factor=1_000_000)
        interface = UAInterface(strategy)

        with self.assertRaises(InvalidTokenError):
            await interface.get_subscription(token="invalidToken")
        # Tokens starting with "f" in dry-run mode simulate an "internal"
        # error.
        with self.assertRaises(CheckSubscriptionError):
            await interface.get_subscription(token="failure")

        # Tokens starting with "x" is dry-run mode simulate an expired token.
        with self.assertRaises(ExpiredTokenError):
            await interface.get_subscription(token="xpiredToken")

        # Other tokens are considered valid in dry-run mode.
        await interface.get_subscription(token="validToken")

    async def test_get_subscription(self):
        # We use the standard strategy but don't actually run it
        strategy = UAClientUAInterfaceStrategy()
        interface = UAInterface(strategy)

        status = {
            "account": {
                "name": "user@domain.com",
            },
            "contract": {
                "name": "UA Apps - Essential (Virtual)",
            },
            "expires": "2035-12-31T00:00:00+00:00",
            "services": [
                {
                    "name": "cis",
                    "description": "Center for Internet Security Audit Tools",
                    "entitled": "no",
                    "auto_enabled": "no",
                    "available": "yes",
                },
                {
                    "name": "esm-apps",
                    "description": "UA Apps: Extended Security Maintenance (ESM)",
                    "entitled": "yes",
                    "auto_enabled": "yes",
                    "available": "no",
                },
                {
                    "name": "esm-infra",
                    "description": "UA Infra: Extended Security Maintenance (ESM)",
                    "entitled": "yes",
                    "auto_enabled": "yes",
                    "available": "yes",
                },
                {
                    "name": "fips",
                    "description": "NIST-certified core packages",
                    "entitled": "yes",
                    "auto_enabled": "no",
                    "available": "yes",
                },
            ],
        }
        interface.get_subscription_status = AsyncMock(return_value=status)
        subscription = await interface.get_subscription(token="XXX")

        self.assertIn(
            UbuntuProService(
                name="esm-infra",
                description="UA Infra: Extended Security Maintenance (ESM)",
                auto_enabled=True,
            ),
            subscription.services,
        )
        self.assertIn(
            UbuntuProService(
                name="fips",
                description="NIST-certified core packages",
                auto_enabled=False,
            ),
            subscription.services,
        )
        self.assertNotIn(
            UbuntuProService(
                name="esm-apps",
                description="UA Apps: Extended Security Maintenance (ESM)",
                auto_enabled=True,
            ),
            subscription.services,
        )
        self.assertNotIn(
            UbuntuProService(
                name="cis",
                description="Center for Internet Security Audit Tools",
                auto_enabled=False,
            ),
            subscription.services,
        )

        # Test with "Z" suffix for the expiration date.
        status["expires"] = "2035-12-31T00:00:00Z"
        subscription = await interface.get_subscription(token="XXX")
