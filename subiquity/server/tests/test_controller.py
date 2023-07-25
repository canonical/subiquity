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
from unittest.mock import patch

from subiquity.server.controller import SubiquityController
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app


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
        self.controller.autoinstall_default = "default-data"
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
        self.controller.setup_autoinstall()
        mock_load.assert_called_once_with("default-data")
