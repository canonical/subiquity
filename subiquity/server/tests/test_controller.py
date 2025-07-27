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

import contextlib
from unittest.mock import AsyncMock, patch

from subiquity.server.autoinstall import AutoinstallValidationError
from subiquity.server.controller import NonInteractiveController, SubiquityController
from subiquity.server.types import InstallerChannels
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized


class TestController(SubiTestCase):
    def setUp(self):
        self.controller = SubiquityController(make_app())
        self.controller.context.child = contextlib.nullcontext

    @patch.object(SubiquityController, "load_autoinstall_data")
    def test_setup_autoinstall(self, mock_load):
        # No autoinstall data
        self.controller.app.autoinstall_config = None
        self.controller.setup_autoinstall()
        mock_load.assert_not_called()

        # Make sure the autoinstall_key has precedence over
        # autoinstall_key_alias if both are present.
        self.controller.app.autoinstall_config = {
            "sample": "some-sample-data",
            "sample-alias": "some-sample-alias-data",
        }
        self.controller.autoinstall_key = "sample"
        self.controller.autoinstall_key_alias = "sample-alias"
        self.controller.setup_autoinstall()
        mock_load.assert_called_once_with("some-sample-data")

        # Make sure we failover to autoinstall_key_alias if autoinstall_key is
        # not present
        mock_load.reset_mock()
        self.controller.autoinstall_key = "inexistent"
        self.controller.setup_autoinstall()
        mock_load.assert_called_once_with("some-sample-alias-data")

        # Make sure we failover to autoinstall_default otherwise
        mock_load.reset_mock()
        self.controller.autoinstall_key = "inexistent"
        self.controller.autoinstall_key_alias = "inexistent"
        self.controller.autoinstall_default = "default-data"
        self.controller.setup_autoinstall()
        mock_load.assert_called_once_with("default-data")

    def test_autoinstall_validation(self):
        """Test validation error type and no apport reporting"""

        self.controller.autoinstall_schema = {
            "type": "object",
            "properties": {
                "some-key": {
                    "type": "boolean",
                },
            },
        }

        self.bad_ai_data = {"some-key": "not a bool"}

        self.controller.autoinstall_key = "some-key"

        # Assert error type is correct
        with self.assertRaises(AutoinstallValidationError) as ctx:
            self.controller.validate_autoinstall(self.bad_ai_data)

        exception = ctx.exception

        # Assert error section is based on autoinstall_key
        self.assertEqual(exception.owner, "some-key")

        # Assert apport report is not created
        # This only checks that controllers do not manually create an apport
        # report on validation. Should also be tested in Server
        self.controller.app.make_apport_report.assert_not_called()


class TestControllerInteractive(SubiTestCase):
    def setUp(self):
        self.controller = SubiquityController(make_app())
        self.controller.autoinstall_key = "mock"
        self.controller.autoinstall_key_alias = "mock-alias"

    def test_interactive_with_no_autoinstall(self):
        """Test the controller is interactive when not autoinstalling."""
        self.controller.app.autoinstall_config = {}
        self.assertTrue(self.controller.interactive())

    @parameterized.expand(
        (
            (True, {"interactive-sections": ["mock"]}),
            (True, {"interactive-sections": ["mock-alias"]}),
            (True, {"interactive-sections": ["*"]}),
            (False, {"interactive-sections": ["not-mock"]}),
            (False, {"interactive-sections": []}),
        )
    )
    def test_interactive_sections(self, interactive, config):
        """Test controller interactivity honors interactive-sections."""
        self.controller.app.autoinstall_config = config
        self.assertEqual(interactive, self.controller.interactive())

    def test_interactive_returns_state_variable(self):
        """Test interactive returns the _active state variable."""
        self.controller._active = False
        # By default _active is True, but can be modified by _confirmed for
        # interactive_for_variants functionality.
        self.controller.app.autoinstall_config = {}
        self.assertFalse(self.controller.interactive())

    def test_interactive_fallthrough_is_false(self):
        """Test interactive returns False as the fallthrough return.

        bool(None) == False, but None != False. This feels like a bug waiting
        to happen. Let's really make sure it's False.
        """
        self.controller.app.autoinstall_config = {"mocked": "stuff"}
        self.assertEqual(False, self.controller.interactive())
        self.assertNotEqual(None, self.controller.interactive())


class TestNonInteractiveControllerInteractive(SubiTestCase):
    def setUp(self):
        self.controller = NonInteractiveController(make_app())
        self.controller.autoinstall_key = "mock"
        self.controller.autoinstall_key_alias = "mock-alias"

    @parameterized.expand(
        (
            ({},),
            ({"interactive-sections": ["mock"]},),
            ({"interactive-sections": ["mock-alias"]},),
            ({"interactive-sections": ["*"]},),
            ({"interactive-sections": ["not-mock"]},),
            ({"interactive-sections": []},),
        )
    )
    def test_always_non_interactive(self, config):
        """Test NonInteractiveControllers are always non-interactive"""
        self.controller.app.autoinstall_config = config
        self.assertFalse(self.controller.interactive())


class TestInteractiveForVariant(SubiTestCase):
    async def test_no_variant_integration(self):
        """Test no interactive for variant integration by default."""

        class MockController(SubiquityController):
            _confirmed = AsyncMock()

        controller = MockController(make_app())
        self.assertIsNone(controller.interactive_for_variants)

        # Use abroadcast to explicitly block until this broadcast is done
        await controller.app.hub.abroadcast(InstallerChannels.INSTALL_CONFIRMED)
        controller._confirmed.assert_not_awaited()

    async def test_variant_integration_subscription(self):
        """Test _confirmed is called when interative for variants is supported."""

        class MockController(SubiquityController):
            _confirmed = AsyncMock()
            interactive_for_variants = ["mock-server"]

        controller = MockController(make_app())

        # Use abroadcast to explicitly block until this broadcast is done
        await controller.app.hub.abroadcast(InstallerChannels.INSTALL_CONFIRMED)
        controller._confirmed.assert_awaited()

    @parameterized.expand(
        (
            (True, "mock-server", ["mock-server", "mock-desktop"]),
            (True, "mock-desktop", ["mock-server", "mock-desktop"]),
            (False, "mock-core", ["mock-server", "mock-desktop"]),
        )
    )
    async def test_variant_confirmed_call(self, active, app_variant, variant_support):
        """Test no interactive for variant integration by default."""

        class MockController(SubiquityController):
            configured = AsyncMock()
            interactive_for_variants = variant_support

        controller = MockController(make_app())
        controller.app.base_model.source.current.variant = app_variant

        await controller._confirmed()
        if active:
            controller.configured.assert_not_awaited()
            self.assertTrue(controller._active)
        else:
            controller.configured.assert_awaited()
            self.assertFalse(controller._active)
