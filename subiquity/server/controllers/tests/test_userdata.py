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

import os
import unittest
from pathlib import Path
from unittest import mock

import jsonschema
from jsonschema.validators import validator_for

from subiquity.cloudinit import CloudInitSchemaValidationError
from subiquity.models.subiquity import SubiquityModel
from subiquity.server.controllers.userdata import UserdataController
from subiquity.server.server import INSTALL_MODEL_NAMES, POSTINSTALL_MODEL_NAMES
from subiquitycore.pubsub import MessageHub
from subiquitycore.tests.mocks import make_app


# Patch os.environ for system_scripts
@mock.patch.dict(os.environ, {"SNAP": str(Path(__file__).parents[4])})
class TestUserdataController(unittest.TestCase):
    def setUp(self):
        base_model = SubiquityModel(
            "test",
            MessageHub(),
            INSTALL_MODEL_NAMES,
            POSTINSTALL_MODEL_NAMES,
            dry_run=True,
        )
        self.app = make_app(model=base_model)
        self.controller = UserdataController(self.app)
        self.controller.model = None

    def test_load_autoinstall_data(self):
        with self.subTest("Valid user-data resets userdata model"):
            valid_schema = {"ssh_import_id": ["you"]}
            self.controller.model = {"some": "old userdata"}
            self.controller.load_autoinstall_data(valid_schema)
            self.assertEqual(self.controller.model, valid_schema)

        fake_error = CloudInitSchemaValidationError(
            "ssh_import_id: 'wrong' is not of type 'array'"
        )
        invalid_schema = {"ssh_import_id": "wrong"}
        validate = self.controller.app.base_model.validate_cloudconfig_schema = (
            mock.Mock()
        )
        validate.side_effect = fake_error
        with self.subTest("Invalid user-data raises error"):
            with self.assertRaises(CloudInitSchemaValidationError) as ctx:
                self.controller.load_autoinstall_data(invalid_schema)
            expected_error = "ssh_import_id: 'wrong' is not of" " type 'array'"
            self.assertEqual(expected_error, str(ctx.exception))
            validate.assert_called_with(
                data=invalid_schema, data_source="autoinstall.user-data"
            )

    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            UserdataController.autoinstall_schema
        )

        JsonValidator.check_schema(UserdataController.autoinstall_schema)

    def test_load_none(self):
        self.controller.load_autoinstall_data(None)
        self.assertIsNone(self.controller.model)

    def test_load_empty(self):
        self.controller.load_autoinstall_data({})
        self.assertEqual({}, self.controller.model)

    def test_load_some(self):
        self.controller.load_autoinstall_data({"users": []})
        self.assertEqual({"users": []}, self.controller.model)

    def test_load_bad(self):
        with self.assertRaises(CloudInitSchemaValidationError):
            self.controller.load_autoinstall_data({"stuff": "things"})

        self.assertEqual(None, self.controller.model)
