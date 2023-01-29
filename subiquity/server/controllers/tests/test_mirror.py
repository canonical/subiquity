# Copyright 2021 Canonical, Ltd.
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

import io
import jsonschema
import unittest
from unittest import mock

from subiquitycore.tests.mocks import make_app
from subiquity.models.mirror import MirrorModel
from subiquity.server.apt import AptConfigCheckError
from subiquity.server.controllers.mirror import MirrorController
from subiquity.server.controllers.mirror import log as MirrorLogger


class TestMirrorSchema(unittest.TestCase):
    def validate(self, data):
        jsonschema.validate(data, MirrorController.autoinstall_schema)

    def test_empty(self):
        self.validate({})

    def test_disable_components(self):
        self.validate({'disable_components': ['universe']})

    def test_no_disable_main(self):
        with self.assertRaises(jsonschema.ValidationError):
            self.validate({'disable_components': ['main']})

    def test_no_disable_random_junk(self):
        with self.assertRaises(jsonschema.ValidationError):
            self.validate({'disable_components': ['not-a-component']})


class TestMirrorController(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        app = make_app()
        self.controller = MirrorController(app)
        self.controller.apt_configurer = mock.AsyncMock()

    def test_make_autoinstall(self):
        self.controller.model = MirrorModel()
        self.controller.model.primary_elected = \
            self.controller.model.primary_candidates[0]
        config = self.controller.make_autoinstall()
        self.assertIn("disable_components", config.keys())
        self.assertIn("primary", config.keys())
        self.assertIn("geoip", config.keys())

    async def test_run_mirror_testing(self):
        def fake_mirror_check_success(output):
            output.write("test is successful!")

        def fake_mirror_check_failure(output):
            output.write("Unable to download index")
            raise AptConfigCheckError

        output = io.StringIO()
        mock_source_configured = mock.patch.object(
                self.controller.source_configured_event, "wait")

        mock_run_apt_config_check = mock.patch.object(
                self.controller.apt_configurer, "run_apt_config_check",
                side_effect=fake_mirror_check_success)
        with mock_source_configured, mock_run_apt_config_check:
            await self.controller.run_mirror_testing(output)
        self.assertEqual(output.getvalue(), "test is successful!")

        output = io.StringIO()
        mock_run_apt_config_check = mock.patch.object(
                self.controller.apt_configurer, "run_apt_config_check",
                side_effect=fake_mirror_check_failure)
        with mock_source_configured, mock_run_apt_config_check:
            with self.assertRaises(AptConfigCheckError):
                await self.controller.run_mirror_testing(output)
        self.assertEqual(output.getvalue(), "Unable to download index")

    async def test_try_mirror_checking_once(self):
        run_test = mock.patch.object(self.controller, "run_mirror_testing")
        with run_test:
            with self.assertLogs(MirrorLogger, "DEBUG") as debug:
                await self.controller.try_mirror_checking_once()
        self.assertIn("Mirror checking successful",
                      [record.msg for record in debug.records])
        self.assertIn("APT output follows",
                      [record.msg for record in debug.records])

        run_test = mock.patch.object(self.controller, "run_mirror_testing",
                                     side_effect=AptConfigCheckError)
        with run_test:
            with self.assertLogs(MirrorLogger, "DEBUG") as debug:
                with self.assertRaises(AptConfigCheckError):
                    await self.controller.try_mirror_checking_once()
        self.assertIn("Mirror checking failed",
                      [record.msg for record in debug.records])
        self.assertIn("APT output follows",
                      [record.msg for record in debug.records])
