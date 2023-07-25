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

import unittest

from cloudinit.config.schema import SchemaValidationError

from subiquity.server.controllers.userdata import UserdataController
from subiquitycore.tests.mocks import make_app

try:
    from cloudinit.config.schema import SchemaProblem
except ImportError:

    def SchemaProblem(x, y):
        return (x, y)  # TODO(drop on cloud-init 22.3 SRU)


class TestUserdataController(unittest.TestCase):
    def setUp(self):
        self.controller = UserdataController(make_app())

    def test_load_autoinstall_data(self):
        with self.subTest("Valid user-data resets userdata model"):
            valid_schema = {"ssh_import_id": ["you"]}
            self.controller.model = {"some": "old userdata"}
            self.controller.load_autoinstall_data(valid_schema)
            self.assertEqual(self.controller.model, valid_schema)

        fake_error = SchemaValidationError(
            schema_errors=(
                SchemaProblem("ssh_import_id", "'wrong' is not of type 'array'"),
            ),
        )
        invalid_schema = {"ssh_import_id": "wrong"}
        validate = self.controller.app.base_model.validate_cloudconfig_schema
        validate.side_effect = fake_error
        with self.subTest("Invalid user-data raises error"):
            with self.assertRaises(SchemaValidationError) as ctx:
                self.controller.load_autoinstall_data(invalid_schema)
            expected_error = (
                "Cloud config schema errors: ssh_import_id: 'wrong' is not of"
                " type 'array'"
            )
            self.assertEqual(expected_error, str(ctx.exception))
            validate.assert_called_with(
                data=invalid_schema, data_source="autoinstall.user-data"
            )
