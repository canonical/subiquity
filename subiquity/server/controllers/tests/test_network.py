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

from unittest.mock import ANY, Mock, patch

import jsonschema
from jsonschema.validators import validator_for

from subiquity.server.controllers.network import NetworkController
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app


class TestNetworkController(SubiTestCase):
    def setUp(self):
        app = make_app()
        app.note_file_for_apport = Mock()
        app.opts.output_base = self.tmp_dir()
        app.opts.project = "subiquity"
        self.controller = NetworkController(app)
        self.controller.model.render_config = Mock(return_value=dict())
        self.controller.model.stringify_config = Mock(return_value="")

    def test_netplan_permissions(self):
        """Assert correct netplan config permissions

        Since netplan 0.106.1, Netplan YAMLs should have file
        permissions with mode 0o600 (root/owner RW only).
        """

        with patch("os.getuid", return_value=0):
            with patch("os.chmod") as mock_chmod:
                with patch("os.chown") as mock_chown:
                    self.controller._write_config()
                    mock_chmod.assert_called_with(ANY, 0o600)
                    mock_chown.assert_called_with(ANY, 0, 0)

    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            NetworkController.autoinstall_schema
        )

        JsonValidator.check_schema(NetworkController.autoinstall_schema)
