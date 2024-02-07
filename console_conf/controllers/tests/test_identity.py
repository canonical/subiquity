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
import os.path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from console_conf.controllers.identity import IdentityController
from subiquitycore.models.network import NetworkDev
from subiquitycore.tests.mocks import make_app
from subiquitycore.snapd import get_fake_connection


class TestIdentityController(unittest.TestCase):
    @patch("os.ttyname", return_value="/dev/tty1")
    @patch("console_conf.controllers.identity.get_core_version", return_value="24")
    def test_snap_integration(self, core_version, ttyname):
        with tempfile.TemporaryDirectory(suffix="console-conf-test") as statedir:
            app = make_app()
            app.opts.dry_run = False
            app.snapdcon = get_fake_connection()
            app.state_dir = statedir
            network_model = MagicMock()
            mock_devs = [MagicMock(spec=NetworkDev)]
            network_model.get_all_netdevs.return_value = mock_devs
            mock_devs[0].actual_global_ip_addresses = ["1.2.3.4"]
            app.base_model.network = network_model
            app.urwid_loop = MagicMock()

            def state_path(*parts):
                return os.path.join(statedir, *parts)

            app.state_path = MagicMock(side_effect=state_path)

            create_user_calls = 0

            def create_user_cb(path, body, **args):
                nonlocal create_user_calls
                create_user_calls += 1
                self.assertEqual(path, "v2/users")
                self.assertEqual(
                    body, {"action": "create", "email": "foo@bar.com", "sudoer": True}
                )
                return {
                    "status": "OK",
                    "result": [
                        {
                            "username": "foo",
                        }
                    ],
                }

            # fake POST handlers
            app.snapdcon.post_cb["v2/users"] = create_user_cb

            c = IdentityController(app)
            c.identity_done("foo@bar.com")

            self.assertEqual(create_user_calls, 1)

            with open(os.path.join(statedir, "login-details.txt")) as inf:
                data = inf.read()
            self.assertIn("Ubuntu Core 24 on 1.2.3.4 (tty1)\n", data)
