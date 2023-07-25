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

import contextlib
import io
import unittest
from unittest import mock

import jsonschema

from subiquity.common.types import MirrorSelectionFallback
from subiquity.models.mirror import MirrorModel
from subiquity.server.apt import AptConfigCheckError
from subiquity.server.controllers.mirror import MirrorController, NoUsableMirrorError
from subiquity.server.controllers.mirror import log as MirrorLogger
from subiquitycore.tests.mocks import make_app


class TestMirrorSchema(unittest.TestCase):
    def validate(self, data):
        jsonschema.validate(data, MirrorController.autoinstall_schema)

    def test_empty(self):
        self.validate({})

    def test_disable_components(self):
        self.validate({"disable_components": ["universe"]})

    def test_no_disable_main(self):
        with self.assertRaises(jsonschema.ValidationError):
            self.validate({"disable_components": ["main"]})

    def test_no_disable_random_junk(self):
        with self.assertRaises(jsonschema.ValidationError):
            self.validate({"disable_components": ["not-a-component"]})


class TestMirrorController(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        app = make_app()
        self.controller = MirrorController(app)
        self.controller.test_apt_configurer = mock.AsyncMock()

    def test_make_autoinstall(self):
        self.controller.model = MirrorModel()
        self.controller.model.primary_candidates[0].elect()
        config = self.controller.make_autoinstall()
        self.assertIn("disable_components", config.keys())
        self.assertIn("mirror-selection", config.keys())
        self.assertIn("geoip", config.keys())
        self.assertIn("fallback", config.keys())
        self.assertNotIn("primary", config.keys())

    def test_make_autoinstall_legacy(self):
        self.controller.model = MirrorModel()
        self.controller.model.legacy_primary = True
        self.controller.model.primary_candidates = (
            self.controller.model.get_default_primary_candidates()
        )
        self.controller.model.primary_candidates[0].elect()
        config = self.controller.make_autoinstall()
        self.assertIn("disable_components", config.keys())
        self.assertIn("primary", config.keys())
        self.assertIn("geoip", config.keys())
        self.assertIn("fallback", config.keys())
        self.assertNotIn("mirror-selection", config.keys())

    async def test_run_mirror_testing(self):
        def fake_mirror_check_success(output):
            output.write("test is successful!")

        def fake_mirror_check_failure(output):
            output.write("Unable to download index")
            raise AptConfigCheckError

        output = io.StringIO()
        mock_source_configured = mock.patch.object(
            self.controller.source_configured_event, "wait"
        )

        mock_run_apt_config_check = mock.patch.object(
            self.controller.test_apt_configurer,
            "run_apt_config_check",
            side_effect=fake_mirror_check_success,
        )
        with mock_source_configured, mock_run_apt_config_check:
            await self.controller.run_mirror_testing(output)
        self.assertEqual(output.getvalue(), "test is successful!")

        output = io.StringIO()
        mock_run_apt_config_check = mock.patch.object(
            self.controller.test_apt_configurer,
            "run_apt_config_check",
            side_effect=fake_mirror_check_failure,
        )
        with mock_source_configured, mock_run_apt_config_check:
            with self.assertRaises(AptConfigCheckError):
                await self.controller.run_mirror_testing(output)
        self.assertEqual(output.getvalue(), "Unable to download index")

    async def test_try_mirror_checking_once(self):
        run_test = mock.patch.object(self.controller, "run_mirror_testing")
        with run_test:
            with self.assertLogs(MirrorLogger, "DEBUG") as debug:
                await self.controller.try_mirror_checking_once()
        self.assertIn(
            "Mirror checking successful", [record.msg for record in debug.records]
        )
        self.assertIn("APT output follows", [record.msg for record in debug.records])

        run_test = mock.patch.object(
            self.controller, "run_mirror_testing", side_effect=AptConfigCheckError
        )
        with run_test:
            with self.assertLogs(MirrorLogger, "DEBUG") as debug:
                with self.assertRaises(AptConfigCheckError):
                    await self.controller.try_mirror_checking_once()
        self.assertIn(
            "Mirror checking failed", [record.msg for record in debug.records]
        )
        self.assertIn("APT output follows", [record.msg for record in debug.records])

    @mock.patch("subiquity.server.controllers.mirror.asyncio.sleep")
    async def test_find_and_elect_candidate_mirror(self, mock_sleep):
        self.controller.app.context.child = contextlib.nullcontext
        self.controller.app.base_model.network.has_network = True
        self.controller.model = MirrorModel()
        self.controller.network_configured_event.set()
        self.controller.proxy_configured_event.set()
        self.controller.cc_event.set()

        # Test with no candidate
        self.controller.model.primary_elected = None
        self.controller.model.primary_candidates = []
        with self.assertRaises(NoUsableMirrorError):
            await self.controller.find_and_elect_candidate_mirror(
                self.controller.app.context
            )
        self.assertIsNone(self.controller.model.primary_elected)

        # Test one succeeding candidate
        self.controller.model.primary_elected = None
        self.controller.model.primary_candidates = [
            self.controller.model.create_primary_candidate("http://mirror")
        ]
        with mock.patch.object(self.controller, "try_mirror_checking_once"):
            await self.controller.find_and_elect_candidate_mirror(
                self.controller.app.context
            )
        self.assertEqual(self.controller.model.primary_elected.uri, "http://mirror")

        # Test one succeeding candidate, on second try
        self.controller.model.primary_elected = None
        self.controller.model.primary_candidates = [
            self.controller.model.create_primary_candidate("http://mirror")
        ]
        with mock.patch.object(
            self.controller,
            "try_mirror_checking_once",
            side_effect=(AptConfigCheckError, None),
        ):
            await self.controller.find_and_elect_candidate_mirror(
                self.controller.app.context
            )
        self.assertEqual(self.controller.model.primary_elected.uri, "http://mirror")

        # Test with a single candidate, failing twice
        self.controller.model.primary_elected = None
        self.controller.model.primary_candidates = [
            self.controller.model.create_primary_candidate("http://mirror")
        ]
        with mock.patch.object(
            self.controller, "try_mirror_checking_once", side_effect=AptConfigCheckError
        ):
            with self.assertRaises(NoUsableMirrorError):
                await self.controller.find_and_elect_candidate_mirror(
                    self.controller.app.context
                )
        self.assertIsNone(self.controller.model.primary_elected)

        # Test with one candidate failing twice, then one succeeding
        self.controller.model.primary_elected = None
        self.controller.model.primary_candidates = [
            self.controller.model.create_primary_candidate("http://failed"),
            self.controller.model.create_primary_candidate("http://success"),
        ]
        with mock.patch.object(
            self.controller,
            "try_mirror_checking_once",
            side_effect=(AptConfigCheckError, AptConfigCheckError, None),
        ):
            await self.controller.find_and_elect_candidate_mirror(
                self.controller.app.context
            )
        self.assertEqual(self.controller.model.primary_elected.uri, "http://success")

        # Test with an unresolved country mirror
        self.controller.model.primary_elected = None
        self.controller.model.primary_candidates = [
            self.controller.model.create_primary_candidate(
                uri=None, country_mirror=True
            ),
            self.controller.model.create_primary_candidate("http://success"),
        ]
        with mock.patch.object(self.controller, "try_mirror_checking_once"):
            await self.controller.find_and_elect_candidate_mirror(
                self.controller.app.context
            )
        self.assertEqual(self.controller.model.primary_elected.uri, "http://success")

    async def test_find_and_elect_candidate_mirror_no_network(self):
        self.controller.app.context.child = contextlib.nullcontext
        self.controller.app.base_model.network.has_network = False
        self.controller.model = MirrorModel()
        self.controller.network_configured_event.set()
        self.controller.proxy_configured_event.set()
        self.controller.cc_event.set()

        await self.controller.find_and_elect_candidate_mirror(
            self.controller.app.context
        )
        self.assertIsNone(self.controller.model.primary_elected)

    async def test_apply_fallback(self):
        model = self.controller.model = MirrorModel()
        app = self.controller.app

        model.fallback = MirrorSelectionFallback.ABORT
        with self.assertRaises(RuntimeError):
            await self.controller.apply_fallback()

        model.fallback = MirrorSelectionFallback.OFFLINE_INSTALL
        app.base_model.network.force_offline = False
        await self.controller.apply_fallback()
        self.assertTrue(app.base_model.network.force_offline)

        model.fallback = MirrorSelectionFallback.CONTINUE_ANYWAY
        app.base_model.network.force_offline = False
        await self.controller.apply_fallback()
        self.assertFalse(app.base_model.network.force_offline)

    async def test_run_mirror_selection_or_fallback(self):
        controller = self.controller

        with mock.patch.object(controller, "apply_fallback") as mock_fallback:
            with mock.patch.object(
                controller,
                "find_and_elect_candidate_mirror",
                side_effect=[None, NoUsableMirrorError],
            ):
                await controller.run_mirror_selection_or_fallback(context=None)
                mock_fallback.assert_not_called()
                await controller.run_mirror_selection_or_fallback(context=None)
                mock_fallback.assert_called_once()
