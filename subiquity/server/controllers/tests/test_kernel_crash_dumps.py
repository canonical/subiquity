# Copyright 2024 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import jsonschema
from jsonschema.validators import validator_for

from subiquity.models.kernel_crash_dumps import KernelCrashDumpsModel
from subiquity.server.autoinstall import AutoinstallValidationError
from subiquity.server.controllers.kernel_crash_dumps import KernelCrashDumpsController
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized


class TestKernelCrashDumpsSchema(SubiTestCase):
    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            KernelCrashDumpsController.autoinstall_schema
        )

        JsonValidator.check_schema(KernelCrashDumpsController.autoinstall_schema)


class TestKernelCrashDumpsAutoinstall(SubiTestCase):
    def setUp(self):
        app = make_app()
        self.controller = KernelCrashDumpsController(app)
        self.controller.model = KernelCrashDumpsModel()

    @parameterized.expand(
        (
            # (config, valid)
            # Valid configs
            ({"enabled": True}, True),
            ({"enabled": False}, True),
            ({"enabled": None}, True),
            # Invalid configs
            ({}, False),
        )
    )
    def test_valid_configs(self, config, valid):
        """Test autoinstall config validation behavior."""
        if valid:
            self.controller.validate_autoinstall(config)
        else:
            with self.assertRaises(AutoinstallValidationError):
                self.controller.validate_autoinstall(config)

    def test_make_autoinstall__default_empty(self):
        self.assertEqual(self.controller.make_autoinstall(), {})

    def test_make_autoinstall__non_default_format(self):
        self.controller.model.enabled = False
        expected = {"enabled": False}
        self.assertEqual(self.controller.make_autoinstall(), expected)
