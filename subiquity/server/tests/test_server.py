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

import copy
import os
import shlex
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import jsonschema
import yaml
from jsonschema.validators import validator_for

from subiquity.cloudinit import CloudInitSchemaTopLevelKeyError
from subiquity.common.types import NonReportableError, PasswordKind
from subiquity.server.autoinstall import AutoinstallError, AutoinstallValidationError
from subiquity.server.nonreportable import NonReportableException
from subiquity.server.server import (
    NOPROBERARG,
    MetaController,
    SubiquityServer,
    cloud_autoinstall_path,
    iso_autoinstall_path,
    root_autoinstall_path,
)
from subiquitycore.context import Context
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized
from subiquitycore.utils import run_command


class TestAutoinstallLoad(SubiTestCase):
    async def asyncSetUp(self):
        self.tempdir = self.tmp_dir()
        os.makedirs(self.tempdir + "/cdrom", exist_ok=True)
        opts = Mock()
        opts.dry_run = True
        opts.output_base = self.tempdir
        opts.machine_config = "examples/machines/simple.json"
        opts.kernel_cmdline = {}
        opts.autoinstall = None
        self.server = SubiquityServer(opts, None)
        self.server.base_model = Mock()
        self.server.base_model.root = opts.output_base

    def path(self, relative_path):
        return self.tmp_path(relative_path, dir=self.tempdir)

    def create(self, path, contents):
        path = self.path(path)
        with open(path, "w") as fp:
            fp.write(contents)
        return path

    def test_autoinstall_disabled(self):
        self.server.opts.autoinstall = ""
        self.server.kernel_cmdline = {"subiquity.autoinstallpath": "kernel"}
        self.create(root_autoinstall_path, "root")
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.assertIsNone(self.server.select_autoinstall())

    def test_arg_wins(self):
        arg = self.create(self.path("arg.autoinstall.yaml"), "arg")
        self.server.opts.autoinstall = arg
        kernel = self.create(self.path("kernel.autoinstall.yaml"), "kernel")
        self.server.kernel_cmdline = {"subiquity.autoinstallpath": kernel}
        root = self.create(root_autoinstall_path, "root")
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "arg")

    def test_kernel_wins(self):
        self.server.opts.autoinstall = None
        kernel = self.create(self.path("kernel.autoinstall.yaml"), "kernel")
        self.server.kernel_cmdline = {"subiquity.autoinstallpath": kernel}
        root = self.create(root_autoinstall_path, "root")
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "kernel")

    def test_root_wins(self):
        self.server.opts.autoinstall = None
        self.server.kernel_cmdline = {}
        root = self.create(root_autoinstall_path, "root")
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "root")

    def test_cloud_wins(self):
        self.server.opts.autoinstall = None
        self.server.kernel_cmdline = {}
        root = self.path(root_autoinstall_path)
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "cloud")

    def test_iso_wins(self):
        self.server.opts.autoinstall = None
        self.server.kernel_cmdline = {}
        root = self.path(root_autoinstall_path)
        # No cloud config file
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "iso")

    def test_nobody_wins(self):
        self.assertIsNone(self.server.select_autoinstall())

    def test_bogus_autoinstall_argument(self):
        self.server.opts.autoinstall = self.path("nonexistant.yaml")
        with self.assertRaises(Exception):
            self.server.select_autoinstall()

    # Only care about changes to autoinstall, not validity
    @patch("subiquity.server.server.SubiquityServer.validate_autoinstall")
    def test_early_commands_changes_autoinstall(self, validate_mock):
        self.server.controllers = Mock()
        self.server.controllers.instances = []
        rootpath = self.path(root_autoinstall_path)

        cmd = f"sed -i -e '$ a stuff: things' {rootpath}"
        contents = f"""\
version: 1
early-commands: ["{cmd}"]
"""
        arg = self.create(self.path("arg.autoinstall.yaml"), contents)
        self.server.opts.autoinstall = arg

        self.server.autoinstall = self.server.select_autoinstall()
        self.server.load_autoinstall_config(only_early=True)
        before_early = {"version": 1, "early-commands": [cmd]}
        self.assertEqual(before_early, self.server.autoinstall_config)
        run_command(shlex.split(cmd), check=True)

        self.server.load_autoinstall_config(only_early=False)
        after_early = {"version": 1, "early-commands": [cmd], "stuff": "things"}
        self.assertEqual(after_early, self.server.autoinstall_config)


class TestAutoinstallValidation(SubiTestCase):
    async def asyncSetUp(self):
        self.tempdir = self.tmp_dir()
        opts = Mock()
        opts.dry_run = True
        opts.output_base = self.tmp_dir()
        opts.machine_config = "examples/machines/simple.json"
        self.server = SubiquityServer(opts, None)
        self.server.base_schema = {
            "type": "object",
            "properties": {
                "some-key": {
                    "type": "boolean",
                },
            },
        }
        self.server.make_apport_report = Mock()

    def path(self, relative_path):
        return self.tmp_path(relative_path, dir=self.tempdir)

    def create(self, path, contents):
        path = self.path(path)
        with open(path, "w") as fp:
            fp.write(contents)
        return path

    # Pseudo Load Controllers to avoid patching the loading logic for each
    # controller when we still want access to class attributes
    def pseudo_load_controllers(self):
        controller_classes = []
        for prefix in self.server.controllers.controller_names:
            controller_classes.append(
                self.server.controllers._get_controller_class(prefix)
            )
        self.server.controllers.instances = controller_classes

    def load_config_and_controllers(
        self, config: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Loads an autoinstall config and controllers.

        Loads the provided autoinstall config and the controllers.
        Returns the valid and invalid portions of the config.
        """
        # Reset base schema
        self.server.base_schema = SubiquityServer.base_schema

        self.server.autoinstall_config = config

        self.pseudo_load_controllers()

        return self.server.filter_autoinstall(config)

    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            SubiquityServer.base_schema
        )

        JsonValidator.check_schema(SubiquityServer.base_schema)

    async def test_skip_cloud_init_config_when_disabled(self):
        """Avoid reading combined-cloud-config when cloud-init disabled."""
        opts = Mock()
        opts.dry_run = True
        self.tempdir = self.tmp_dir()
        opts.output_base = self.tempdir
        opts.machine_config = "examples/machines/simple.json"
        server = SubiquityServer(opts, None)
        opts.dry_run = False  # exciting!
        with patch.object(server, "load_cloud_config") as load_cloud_config:
            with self.subTest("Skip load_cloud_config when disabled"):
                with patch("subiquity.server.server.log.debug") as log:
                    with patch(
                        "subiquity.server.server.cloud_init_status_wait",
                        AsyncMock(return_value=(True, "disabled-by-generator")),
                    ):
                        await server.wait_for_cloudinit()
                log.assert_called_with(
                    "Skip cloud-init autoinstall, cloud-init is disabled"
                )
                load_cloud_config.assert_not_called()
            with self.subTest("Perform load_cloud_config when enabled"):
                with patch("subiquity.server.server.log.debug") as log:
                    with patch(
                        "subiquity.server.server.cloud_init_status_wait",
                        AsyncMock(return_value=(True, "enabled")),
                    ):
                        await server.wait_for_cloudinit()
                log.assert_called_with("cloud-init status: %r", "enabled")
                load_cloud_config.assert_called_with()

    def test_autoinstall_validation__error_type(self):
        """Test that bad autoinstall data throws AutoinstallValidationError"""

        bad_ai_data = {"some-key": "not a bool"}
        self.server.autoinstall_config = bad_ai_data

        with self.assertRaises(AutoinstallValidationError):
            self.server.validate_autoinstall()

    async def test_autoinstall_validation__no_error_report(self):
        """Test no apport reporting"""

        exception = AutoinstallValidationError("Mock")

        loop = Mock()
        context = {"exception": exception}

        with patch("subiquity.server.server.log"):
            with patch.object(self.server, "_run_error_cmds"):
                self.server._exception_handler(loop, context)

        self.server.make_apport_report.assert_not_called()
        self.assertIsNone(self.server.fatal_error)
        error = NonReportableError.from_exception(exception)
        self.assertEqual(error, self.server.nonreportable_error)

    @patch("subiquity.server.server.log")
    async def test_autoinstall_validation__strict_top_level_keys_warn(self, log_mock):
        """Test strict top-level key enforcement warnings in v1"""

        bad_ai_data = {
            "version": 1,
            "interactive-sections": ["identity"],
            "apt": "Invalid but deferred",
            "literally-anything": "lmao",
        }

        good, bad = self.load_config_and_controllers(bad_ai_data)

        # OK in Version 1 but ensure warnings and stripped config
        self.server.validate_autoinstall()
        log_mock.warning.assert_called()
        log_mock.error.assert_not_called()
        self.assertEqual(self.server.autoinstall_config, good)
        self.assertEqual(bad, {"literally-anything": "lmao"})

    @patch("subiquity.server.server.log")
    async def test_autoinstall_validation__strict_top_level_keys_error(self, log_mock):
        """Test strict top-level key enforcement errors in v2 or greater"""

        bad_ai_data = {
            "version": 2,
            "interactive-sections": ["identity"],
            "apt": "Invalid but deferred",
            "literally-anything": "lmao",
        }

        self.load_config_and_controllers(bad_ai_data)

        # TODO: remove once V2 is enabled
        self.server.base_schema["properties"]["version"]["maximum"] = 2

        # Not OK in Version >= 2
        with self.assertRaises(AutoinstallValidationError) as ctx:
            self.server.validate_autoinstall()

        self.assertIn("top-level keys", str(ctx.exception))

        log_mock.error.assert_called()
        log_mock.warning.assert_not_called()

    @parameterized.expand(
        (
            (
                # Case 1: extra key "some-bad-key"
                {
                    "version": 1,
                    "interactive-sections": ["identity"],
                    "apt": "...",
                    "some-bad-key": "...",
                },
                {
                    "version": 1,
                    "interactive-sections": ["identity"],
                    "apt": "...",
                },
                {"some-bad-key": "..."},
            ),
            (
                # Case 2: no bad keys
                {
                    "version": 1,
                    "interactive-sections": ["identity"],
                    "apt": "...",
                },
                {
                    "version": 1,
                    "interactive-sections": ["identity"],
                    "apt": "...",
                },
                {},
            ),
            (
                # Case 3: no good keys
                {"some-bad-key": "..."},
                {},
                {"some-bad-key": "..."},
            ),
            (
                # Case 4: aliased keys are okay too
                {"ubuntu-advantage": "..."},
                {"ubuntu-advantage": "..."},
                {},
            ),
        )
    )
    async def test_autoinstall_validation__filter_autoinstall(self, config, good, bad):
        """Test autoinstall config filtering"""

        self.server.base_schema = SubiquityServer.base_schema
        self.pseudo_load_controllers()

        valid, invalid = self.server.filter_autoinstall(config)

        self.assertEqual(valid, good)
        self.assertEqual(invalid, bad)

    @parameterized.expand(
        (
            # Has valid cloud config, no autoinstall
            ({"valid-cloud": "data"}, {}, False),
            # Has valid cloud config and autoinstall, no valid ai in cloud cfg
            (
                {
                    "valid-cloud": "data",
                    "autoinstall": {
                        "version": 1,
                        "interactive-sections": ["identity"],
                    },
                },
                {
                    "version": 1,
                    "interactive-sections": ["identity"],
                },
                False,
            ),
            # Has valid autoinstall directive in cloud config
            (
                {
                    "interactive-sections": "data",
                    "autoinstall": {
                        "version": 1,
                        "interactive-sections": ["identity"],
                    },
                },
                None,  # Doesn't return
                True,
            ),
            # Invalid cloud config key is autoinstall and no autoinstall
            (
                {
                    "interactive-sections": ["identity"],
                },
                None,  # Doesn't return
                True,
            ),
            # Has invalid cloud config key but is not valid autoinstall either
            (
                {
                    "something-else": "data",
                    "autoinstall": {
                        "version": 1,
                        "interactive-sections": ["identity"],
                    },
                },
                {
                    "version": 1,
                    "interactive-sections": ["identity"],
                },
                False,
            ),
        )
    )
    async def test_autoinstall_from_cloud_config(self, cloud_cfg, expected, throws):
        """Test autoinstall extract from cloud config."""

        self.server.base_schema = SubiquityServer.base_schema
        self.pseudo_load_controllers()

        cloud_data = copy.copy(cloud_cfg)
        cloud_data.pop("valid-cloud", None)
        cloud_data.pop("autoinstall", None)

        with patch(
            "subiquity.server.server.validate_cloud_init_top_level_keys"
        ) as val_mock:
            if len(cloud_data) == 0:
                val_mock.return_value = True
            else:
                val_mock.side_effect = CloudInitSchemaTopLevelKeyError(
                    keys=list(cloud_data.keys())
                )

            if throws:
                with self.assertRaises(AutoinstallError):
                    cfg = await self.server._extract_autoinstall_from_cloud_config(
                        cloud_cfg=cloud_cfg
                    )
            else:
                cfg = await self.server._extract_autoinstall_from_cloud_config(
                    cloud_cfg=cloud_cfg
                )

                self.assertEqual(cfg, expected)

    async def test_cloud_config_extract_KeyError(self):
        """Test autoinstall extract from cloud config resilient to missing data."""

        self.server.base_schema = SubiquityServer.base_schema
        self.pseudo_load_controllers()

        with patch(
            "subiquity.server.server.validate_cloud_init_top_level_keys"
        ) as val_mock:
            val_mock.side_effect = CloudInitSchemaTopLevelKeyError(
                keys=["broadcast", "foobar"],
            )

            # Don't throw on keys that error but aren't in the combined config
            cfg = await self.server._extract_autoinstall_from_cloud_config(cloud_cfg={})

            self.assertEqual(cfg, {})

    async def test_autoinstall_validation__top_level_autoinstall(self):
        """Test allow autoinstall as top-level key"""

        new_style = {
            "autoinstall": {
                "version": 1,
                "interactive-sections": ["identity"],
                "apt": "...",
            }
        }
        old_style = new_style["autoinstall"]

        # Read new style correctly
        path = self.create("autoinstall.yaml", yaml.dump(new_style))
        self.assertEqual(self.server._read_config(cfg_path=path), old_style)

        # No changes to old style
        path = self.create("autoinstall.yaml", yaml.dump(old_style))
        self.assertEqual(self.server._read_config(cfg_path=path), old_style)

    async def test_autoinstall_validation__not_cloudinit_datasource(self):
        """Test no cloud init datasources in new style autoinstall"""

        new_style = {
            "autoinstall": {
                "version": 1,
                "interactive-sections": ["identity"],
                "apt": "...",
            },
            "cloudinit-data": "I am data",
        }

        with self.assertRaises(AutoinstallValidationError) as ctx:
            path = self.create("autoinstall.yaml", yaml.dump(new_style))
            self.server._read_config(cfg_path=path)

        self.assertEqual("top-level keys", ctx.exception.owner)


class TestMetaController(SubiTestCase):
    async def test_interactive_sections_not_present(self):
        mc = MetaController(make_app())
        mc.app.autoinstall_config = None
        self.assertIsNone(await mc.interactive_sections_GET())

    async def test_interactive_sections_empty(self):
        mc = MetaController(make_app())
        mc.app.autoinstall_config["interactive-sections"] = []
        self.assertEqual([], await mc.interactive_sections_GET())

    async def test_interactive_sections_all(self):
        mc = MetaController(make_app())
        mc.app.autoinstall_config["interactive-sections"] = ["*"]
        mc.app.controllers.instances = [
            Mock(autoinstall_key="f", interactive=Mock(return_value=False)),
            Mock(autoinstall_key=None, interactive=Mock(return_value=True)),
            Mock(autoinstall_key="t", interactive=Mock(return_value=True)),
        ]
        self.assertEqual(["t"], await mc.interactive_sections_GET())

    async def test_interactive_sections_one(self):
        mc = MetaController(make_app())
        mc.app.autoinstall_config["interactive-sections"] = ["network"]
        self.assertEqual(["network"], await mc.interactive_sections_GET())


class TestDefaultUser(SubiTestCase):
    @patch(
        "subiquity.server.server.user_key_fingerprints",
        Mock(side_effect=Exception("should not be called")),
    )
    async def test_no_default_user(self):
        opts = Mock()
        opts.dry_run = True
        opts.output_base = self.tmp_dir()
        opts.machine_config = "examples/machines/simple.json"
        server = SubiquityServer(opts, None)
        server._user_has_password = Mock(side_effect=Exception("should not be called"))

        opts.dry_run = False  # exciting!
        server.set_installer_password()
        self.assertIsNone(server.installer_user_name)
        self.assertEqual(PasswordKind.NONE, server.installer_user_passwd_kind)


class TestExceptionHandling(SubiTestCase):
    async def asyncSetUp(self):
        opts = Mock()
        opts.dry_run = True
        opts.output_base = self.tmp_dir()
        opts.machine_config = "examples/machines/simple.json"
        self.server = SubiquityServer(opts, None)
        self.server._run_error_cmds = AsyncMock()
        self.server.make_apport_report = Mock()

    async def test_suppressed_apport_reporting(self):
        """Test apport reporting suppressed"""

        MockException = type("MockException", (NonReportableException,), {})
        exception = MockException("Don't report me")
        loop = Mock()
        context = {"exception": exception}

        self.server._exception_handler(loop, context)

        self.server.make_apport_report.assert_not_called()
        self.assertEqual(self.server.fatal_error, None)
        error = NonReportableError.from_exception(exception)
        self.assertEqual(error, self.server.nonreportable_error)

    async def test_not_suppressed_apport_reporting(self):
        """Test apport reporting not suppressed"""

        exception = Exception("Report me")
        loop = Mock()
        context = {"exception": exception}

        self.server._exception_handler(loop, context)

        self.server.make_apport_report.assert_called()
        self.assertIsNotNone(self.server.fatal_error)
        self.assertIsNone(self.server.nonreportable_error)


class TestEventReporting(SubiTestCase):
    async def asyncSetUp(self):
        opts = Mock()
        opts.dry_run = True
        opts.output_base = self.tmp_dir()
        opts.machine_config = NOPROBERARG
        self.server = SubiquityServer(opts, None)

    @parameterized.expand(
        (
            # A very tedious to read truth table for testing
            # behavior. A value of None should mean another
            # option is shadowing the importance of that value
            # ex: in the is-install-context it doesn't matter
            # if it came from a controller. Except interactive=None
            # is a valid value.
            #
            #
            #  -> Special "is-install-context" to force logging
            # |     -> Install is interactive
            # |    |      -> Comes from a controller
            # |    |     |      -> That controller is interactive
            # |    |     |     |      -> Expected to send
            # |    |     |     |     |
            (True, True, None, None, True),
            (True, False, None, None, True),
            (True, None, None, None, True),
            (False, True, None, None, False),
            (False, True, True, True, False),
            (False, True, True, False, True),
            (False, False, False, None, True),
        )
    )
    async def test_maybe_push_to_journal(
        self,
        is_install_context,
        interactive,
        from_controller,
        controller_is_interactive,
        expected_to_send,
    ):
        context: Context = Context(
            self.server, "MockContext", "description", None, "INFO"
        )

        context.set("is-install-context", is_install_context)
        self.server.interactive = interactive
        if from_controller:
            controller = Mock()
            controller.interactive = lambda: controller_is_interactive
            context.set("controller", controller)

        with patch("subiquity.server.server.journal.send") as journal_send_mock:
            self.server._maybe_push_to_journal(
                "event_type", context, context.description
            )
        if expected_to_send:
            journal_send_mock.assert_called_once()
        else:
            journal_send_mock.assert_not_called()

    @parameterized.expand(
        (
            # interactive, pushed to journal
            (True, False),
            (None, False),
            (False, True),
        )
    )
    def test_push_info_events(self, interactive, expect_pushed):
        """Test info event publication"""

        context: Context = Context(
            self.server, "MockContext", "description", None, "INFO"
        )
        self.server.interactive = interactive

        with patch("subiquity.server.server.journal.send") as journal_send_mock:
            self.server.report_info_event(context, "message")

        if not expect_pushed:
            journal_send_mock.assert_not_called()
        else:
            journal_send_mock.assert_called_once()
            # message is the only positional argument
            (message,) = journal_send_mock.call_args.args
            self.assertIn("message", message)
            self.assertNotIn("description", message)

    @parameterized.expand(
        (
            # interactive
            (True,),
            (None,),
            (False,),
        )
    )
    def test_push_warning_events(self, interactive):
        """Test warning event publication"""

        context: Context = Context(
            self.server, "MockContext", "description", None, "INFO"
        )
        self.server.interactive = interactive

        with patch("subiquity.server.server.journal.send") as journal_send_mock:
            self.server.report_warning_event(context, "message")

        journal_send_mock.assert_called_once()
        # message is the only positional argument
        (message,) = journal_send_mock.call_args.args
        self.assertIn("message", message)
        self.assertNotIn("description", message)

    @parameterized.expand(
        (
            # interactive
            (True,),
            (None,),
            (False,),
        )
    )
    def test_push_error_events(self, interactive):
        """Test error event publication"""

        context: Context = Context(
            self.server, "MockContext", "description", None, "INFO"
        )
        self.server.interactive = interactive

        with patch("subiquity.server.server.journal.send") as journal_send_mock:
            self.server.report_error_event(context, "message")

        journal_send_mock.assert_called_once()
        # message is the only positional argument
        (message,) = journal_send_mock.call_args.args
        self.assertIn("message", message)
        self.assertNotIn("description", message)
