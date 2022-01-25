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

from subprocess import CalledProcessError, CompletedProcess
import unittest
from unittest.mock import patch

from subiquity.common.ubuntu_advantage import (
    InvalidUATokenError,
    ExpiredUATokenError,
    CheckSubscriptionError,
    UAInterface,
    MockedUAInterfaceStrategy,
    UAClientUAInterfaceStrategy,
    )
from subiquitycore.tests.util import run_coro


class TestMockedUAInterfaceStrategy(unittest.TestCase):
    def setUp(self):
        self.strategy = MockedUAInterfaceStrategy(scale_factor=1_000_000)

    def test_query_info_invalid(self):
        # Tokens starting with "i" in dry-run mode cause the token to be
        # reported as invalid.
        with self.assertRaises(InvalidUATokenError):
            run_coro(self.strategy.query_info(token="invalidToken"))

    def test_query_info_failure(self):
        # Tokens starting with "f" in dry-run mode simulate an "internal"
        # error.
        with self.assertRaises(CheckSubscriptionError):
            run_coro(self.strategy.query_info(token="failure"))

    def test_query_info_expired(self):
        # Tokens starting with "x" is dry-run mode simulate an expired token.
        info = run_coro(self.strategy.query_info(token="xpiredToken"))
        self.assertEqual(info["expires"], "2010-12-31T00:00:00+00:00")

    def test_query_info_valid(self):
        # Other tokens are considered valid in dry-run mode.
        info = run_coro(self.strategy.query_info(token="validToken"))
        self.assertEqual(info["expires"], "2035-12-31T00:00:00+00:00")


class TestUAClientUAInterfaceStrategy(unittest.TestCase):
    arun_command = "subiquity.common.ubuntu_advantage.utils.arun_command"

    def test_init(self):
        # Default initializer.
        strategy = UAClientUAInterfaceStrategy()
        self.assertEqual(strategy.executable, ["ubuntu-advantage"])

        # Initialize with a mere path.
        strategy = UAClientUAInterfaceStrategy("/usr/bin/ubuntu-advantage")
        self.assertEqual(strategy.executable, ["/usr/bin/ubuntu-advantage"])

        # Initialize with a path + interpreter.
        strategy = UAClientUAInterfaceStrategy(
            ("python3", "/usr/bin/ubuntu-advantage")
        )
        self.assertEqual(strategy.executable,
                         ["python3", "/usr/bin/ubuntu-advantage"])

    def test_query_info_succeeded(self):
        strategy = UAClientUAInterfaceStrategy()
        command = (
            "ubuntu-advantage",
            "status",
            "--format", "json",
            "--simulate-with-token", "123456789",
        )

        with patch(self.arun_command) as mock_arun:
            mock_arun.return_value = CompletedProcess([], 0)
            mock_arun.return_value.stdout = "{}"
            run_coro(strategy.query_info(token="123456789"))
            mock_arun.assert_called_once_with(command, check=True)

    def test_query_info_failed(self):
        strategy = UAClientUAInterfaceStrategy()
        command = (
            "ubuntu-advantage",
            "status",
            "--format", "json",
            "--simulate-with-token", "123456789",
        )

        with patch(self.arun_command) as mock_arun:
            mock_arun.side_effect = CalledProcessError(returncode=1,
                                                       cmd=command)
            mock_arun.return_value.stdout = "{}"
            with self.assertRaises(CheckSubscriptionError):
                run_coro(strategy.query_info(token="123456789"))
            mock_arun.assert_called_once_with(command, check=True)

    def test_query_info_invalid_json(self):
        strategy = UAClientUAInterfaceStrategy()
        command = (
            "ubuntu-advantage",
            "status",
            "--format", "json",
            "--simulate-with-token", "123456789",
        )

        with patch(self.arun_command) as mock_arun:
            mock_arun.return_value = CompletedProcess([], 0)
            mock_arun.return_value.stdout = "invalid-json"
            with self.assertRaises(CheckSubscriptionError):
                run_coro(strategy.query_info(token="123456789"))
            mock_arun.assert_called_once_with(command, check=True)


class TestUAInterface(unittest.TestCase):

    def test_mocked_get_activable_services(self):
        strategy = MockedUAInterfaceStrategy(scale_factor=1_000_000)
        interface = UAInterface(strategy)

        with self.assertRaises(InvalidUATokenError):
            run_coro(interface.get_activable_services(token="invalidToken"))
        # Tokens starting with "f" in dry-run mode simulate an "internal"
        # error.
        with self.assertRaises(CheckSubscriptionError):
            run_coro(interface.get_activable_services(token="failure"))

        # Tokens starting with "x" is dry-run mode simulate an expired token.
        with self.assertRaises(ExpiredUATokenError):
            run_coro(interface.get_activable_services(token="xpiredToken"))

        # Other tokens are considered valid in dry-run mode.
        services = run_coro(
                interface.get_activable_services(token="validToken"))
        for service in services:
            self.assertIn("name", service)
            self.assertIn("description", service)
            self.assertEqual(service["available"], "yes")
            self.assertEqual(service["entitled"], "yes")
