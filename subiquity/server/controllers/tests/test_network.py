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

from copy import copy
from unittest.mock import ANY, AsyncMock, Mock, patch

import jsonschema
from jsonschema.validators import validator_for

from subiquity.models.network import NetworkModel
from subiquity.server.controllers.network import NetworkController
from subiquitycore.models.network import NetworkDev
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized


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

        with (
            patch("os.getuid", return_value=0),
            patch("os.chmod") as mock_chmod,
            patch("os.chown") as mock_chown,
        ):
            self.controller._write_config()
            mock_chmod.assert_called_with(ANY, 0o600)
            mock_chown.assert_called_with(ANY, 0, 0)

    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            NetworkController.autoinstall_schema
        )

        JsonValidator.check_schema(NetworkController.autoinstall_schema)


class TestNetworkAutoDisableInterfaces(SubiTestCase):
    """Tests for automatic disabling of disconnected interfaces."""

    def setUp(self):
        app = make_app()
        app.note_file_for_apport = Mock()
        app.opts.output_base = self.tmp_dir()
        app.opts.project = "subiquity"
        app.package_installer = Mock()
        app.state_path = Mock()
        app.hub = AsyncMock()
        self.controller = NetworkController(app)
        self.controller.model = NetworkModel()

    @parameterized.expand(
        (
            # Interactive, view_shown, expect_updates
            (True, False, True),  # Interactive but not modified: update configs
            (False, False, False),  # Autoinstall case: Don't do anything.
            # Should be handled by autoinstall logic
            (True, True, False),  # Edits made in UI: Don't update
        )
    )
    async def test_disable_on_configured(self, interactive, view_shown, modify):
        """Test disconnected interfaces are disabled on marked configured."""
        # It's possible that we only ever mark the network controller
        # configured (e.g., Desktop) and don't otherwise interact with it
        # when it was supposed to be interactive. Test to make sure
        # disconnected interfaces are still disabled internally.
        self.controller.interactive = Mock(return_value=interactive)
        self.controller.view_shown = view_shown

        live_dev = NetworkDev(self.controller.model, "testdev0", "eth")
        live_config = {"dhcp4": True}
        live_dev.config = copy(live_config)
        live_dev.info = Mock(addresses={"addr": Mock(scope="global")})
        self.controller.model.devices_by_name["testdev0"] = live_dev

        dead_dev = NetworkDev(self.controller.model, "testdev1", "eth")
        dead_config = {"dhcp4": True}
        dead_dev.config = copy(dead_config)
        dead_dev.info = Mock(addresses={})
        self.controller.model.devices_by_name["testdev1"] = dead_dev

        with patch("subiquity.server.controller.open"):
            await self.controller.configured()

        # Live config shouldn't be modified no matter what
        self.assertEqual(live_dev.config, live_config)

        if modify:
            self.assertEqual(dead_dev.config, {})
        else:
            self.assertEqual(dead_dev.config, dead_config)
