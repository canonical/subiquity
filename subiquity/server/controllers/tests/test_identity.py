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

import jsonschema
from jsonschema.validators import validator_for

from subiquity.server.autoinstall import AutoinstallError
from subiquity.server.controllers.identity import IdentityController
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app


class TestIdentityController(SubiTestCase):
    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            IdentityController.autoinstall_schema
        )

        JsonValidator.check_schema(IdentityController.autoinstall_schema)


class TestControllerUserCreationFlows(SubiTestCase):
    # TestUserCreationFlows has more information about user flow use cases.
    # See subiquity/models/tests/test_subiquity.py for details.
    def setUp(self):
        self.app = make_app()
        self.ic = IdentityController(self.app)
        self.ic.model.user = None

    async def test_server_requires_identity_case_4a1(self):
        self.app.base_model.source.current.variant = "server"

        # Autoinstall: no identity or user data and identity is not interactive
        self.app.autoinstall_config = {"interactive-sections": ["not-identity"]}
        with self.assertRaises(AutoinstallError):
            self.ic.load_autoinstall_data(None)

    async def test_server_requires_identity_case_4a1__ok_interactive(self):
        """Test no require identity for interactive identity"""
        self.app.base_model.source.current.variant = "server"

        # Explicitly interactive
        self.app.autoinstall_config = {"interactive-sections": ["identity"]}
        self.ic.load_autoinstall_data(None)

        # Implicitly interactive
        self.app.autoinstall_config = {"interactive-sections": ["*"]}
        self.ic.load_autoinstall_data(None)

        # No Autoinstall => interactive
        self.app.autoinstall_config = {}
        self.ic.load_autoinstall_data(None)

    async def test_server_requires_identity_case_4a1__reset_only_true(self):
        """Test no require identity for reset-partition-only=yes."""
        self.app.base_model.source.current.variant = "server"

        # No raise if reset-parition-only specified
        self.app.autoinstall_config = {
            "storage": {"layout": {"reset-partition-only": True}}
        }
        self.ic.load_autoinstall_data(None)

    async def test_server_requires_identity_case_4a1__reset_only_false(self):
        """Test require identity for reset-partition-only=no."""
        self.app.base_model.source.current.variant = "server"

        # raises if no reset-parition-only in storage:layout:
        self.app.autoinstall_config = {"storage": {"layout": {}}}
        with self.assertRaises(AutoinstallError):
            self.ic.load_autoinstall_data(None)

    async def test_desktop_does_not_require_identity_case_4a2(self):
        self.app.base_model.source.current.variant = "desktop"
        self.ic.load_autoinstall_data(None)
        # should not raise
