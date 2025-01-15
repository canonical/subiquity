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
from subiquity.server.controllers.filesystem import FilesystemController
from subiquity.server.controllers.identity import IdentityController
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized


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
        self.app.opts.bootloader = False
        self.app.controllers.Filesystem = FilesystemController(self.app)
        self.ic = IdentityController(self.app)
        self.ic.model.user = None

    # Test cases for 4a1. Copied for 4a2 but all cases should be valid for desktop.
    test_cases = [
        #  (autoinstall config, valid)
        #
        # No identity or user data section and identity is not interactive
        ({"interactive-sections": ["not-identity"]}, False),
        # Explicitly interactive
        ({"interactive-sections": ["identity"]}, True),
        # Implicitly interactive
        ({"interactive-sections": ["*"]}, True),
        # No Autoinstall => interactive
        ({}, True),
        # Can be missing if reset-partition-only specified
        ({"storage": {"layout": {"reset-partition-only": True}}}, True),
        # Can't be missing if reset-partition-only is not specified
        ({"storage": {"layout": {}}}, False),
        # user-data passed instead
        ({"user-data": "..."}, True),
    ]

    @parameterized.expand(test_cases)
    async def test_server_requires_identity_case_4a1(self, config, valid):
        """Test require identity section on Server"""
        self.app.base_model.source.current.variant = "server"

        self.app.autoinstall_config = config

        if not valid:
            with self.assertRaises(AutoinstallError):
                self.ic.load_autoinstall_data(None)
        else:
            self.ic.load_autoinstall_data(None)

    @parameterized.expand(test_cases)
    async def test_desktop_does_not_require_identity_case_4a2(self, config, valid):
        """Test require identity section on Desktop"""
        self.app.base_model.source.current.variant = "desktop"

        self.app.autoinstall_config = config
        # should never raise
        self.ic.load_autoinstall_data(None)
