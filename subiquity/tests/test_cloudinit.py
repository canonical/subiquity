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

import asyncio
import logging
from subprocess import CalledProcessError, CompletedProcess
from unittest import skipIf
from unittest.mock import Mock, patch

import yaml

from subiquity.cloudinit import (
    CLOUD_INIT_PW_SET,
    CloudInitSchemaTopLevelKeyError,
    CloudInitSchemaValidationError,
    cloud_init_status_wait,
    cloud_init_version,
    get_unknown_keys,
    legacy_cloud_init_extract,
    legacy_cloud_init_validation,
    rand_password,
    rand_user_password,
    read_json_extended_status,
    read_legacy_status,
    supports_format_json,
    supports_recoverable_errors,
    validate_cloud_config_schema,
    validate_cloud_init_top_level_keys,
)
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.parameterized import parameterized


class TestCloudInitVersion(SubiTestCase):
    @parameterized.expand(
        (
            ("23.4-0ubuntu1~23.10.1", "23.4"),
            ("24.1~4gd9677655-0ubuntu1", "24.1"),
            ("23.3.1-1", "23.3.1"),
        )
    )
    def test_split_version(self, pkgver, expected):
        with patch("subiquity.cloudinit.run_command") as rc:
            rc.return_value = Mock()
            rc.return_value.stdout = pkgver
            self.assertEqual(expected, cloud_init_version())

    def test_cloud_init_not_present(self):
        with patch("subiquity.cloudinit.run_command") as rc:
            rc.return_value = Mock()
            rc.return_value.stdout = ""
            self.assertEqual("", cloud_init_version())

    def test_cloud_init_full(self):
        with patch("subiquity.cloudinit.run_command") as rc:
            rc.side_effect = [Mock(stdout="1.2.3"), Mock(stdout="4.5.6")]
            self.assertEqual("1.2.3", cloud_init_version())

    def test_cloud_init_base(self):
        with patch("subiquity.cloudinit.run_command") as rc:
            rc.side_effect = [Mock(stdout=""), Mock(stdout="4.5.6")]
            self.assertEqual("4.5.6", cloud_init_version())

    @parameterized.expand(
        (
            ("22.3", False),
            ("22.4", True),
            ("23.1", True),
        )
    )
    def test_can_status_json(self, civer, expected):
        with patch("subiquity.cloudinit.cloud_init_version") as civ:
            civ.return_value = civer
            self.assertEqual(expected, supports_format_json())

    @parameterized.expand(
        (
            ("23.3", False),
            ("23.4", True),
            ("24.1", True),
        )
    )
    def test_can_show_warnings(self, civer, expected):
        with patch("subiquity.cloudinit.cloud_init_version") as civ:
            civ.return_value = civer
            self.assertEqual(expected, supports_recoverable_errors())

    @skipIf(len(cloud_init_version()) < 1, "cloud-init not found")
    def test_ver_compare(self):
        # purposefully reads from the host system, as a canary warning that the
        # version scheme has changed.
        self.assertGreater(cloud_init_version(), "20.0")

    def test_read_json_extended_status(self):
        jsondata = '{"extended_status": "degraded done", "status": "done"}'
        self.assertEqual("degraded done", read_json_extended_status(jsondata))

    def test_read_json_extended_status_malformed(self):
        self.assertIsNone(read_json_extended_status('{"extended_status"}'))

    def test_read_json_extended_status_empty(self):
        self.assertIsNone(read_json_extended_status(""))

    def test_read_json_status(self):
        jsondata = '{"status": "done"}'
        self.assertEqual("done", read_json_extended_status(jsondata))

    def test_read_legacy_status(self):
        self.assertEqual("disabled", read_legacy_status("status: disabled\n"))

    def test_read_legacy_status_malformed(self):
        self.assertEqual(None, read_legacy_status("status disabled\n"))

    def test_read_legacy_status_empty(self):
        self.assertEqual(None, read_legacy_status("status:\n"))

    def test_read_legacy_status_no_newline(self):
        self.assertEqual("done", read_legacy_status("status: done\n"))

    @patch("subiquity.cloudinit.arun_command", new=Mock())
    @patch("subiquity.cloudinit.asyncio.wait_for")
    async def test_cloud_init_status_wait_timeout(self, m_wait_for):
        # arun_command mocked with regular Mock because the m_wait_for
        # immediate timeout means nobody ever awaits on arun_command.
        # Then this test fails with an obtuse looking RuntimeError.
        m_wait_for.side_effect = asyncio.TimeoutError()
        self.assertEqual((False, "timeout"), await cloud_init_status_wait())

    @patch("subiquity.cloudinit.supports_format_json", new=Mock(return_value=True))
    @patch("subiquity.cloudinit.arun_command", new=Mock())
    @patch("subiquity.cloudinit.asyncio.wait_for")
    async def test_cloud_init_status_wait_json(self, m_wait_for):
        m_wait_for.return_value = CompletedProcess(
            args=[], returncode=0, stdout='{"extended_status": "disabled"}'
        )
        self.assertEqual((True, "disabled"), await cloud_init_status_wait())

    @patch("subiquity.cloudinit.supports_format_json", new=Mock(return_value=False))
    @patch("subiquity.cloudinit.arun_command", new=Mock())
    @patch("subiquity.cloudinit.asyncio.wait_for")
    async def test_cloud_init_status_wait_legacy(self, m_wait_for):
        m_wait_for.return_value = CompletedProcess(
            args=[], returncode=0, stdout="status: done\n"
        )
        self.assertEqual((True, "done"), await cloud_init_status_wait())


@patch("subiquity.cloudinit.system_scripts_env", new=Mock())
class TestCloudInitTopLevelKeyValidation(SubiTestCase):
    @parameterized.expand(
        (
            (
                (
                    "  Error: Cloud config schema errors: : Additional "
                    "properties are not allowed ('bad-key', 'late-commands' "
                    "were unexpected)\n\nError: Invalid schema: user-data\n\n"
                ),
                ["bad-key", "late-commands"],
            ),
            (
                (
                    "  Error: Cloud config schema errors: : Additional "
                    "properties are not allowed ('bad-key' "
                    "was unexpected)\n\nError: Invalid schema: user-data\n\n"
                ),
                ["bad-key"],
            ),
            ("('key_1', 'key-2', 'KEY3' were unexpected)", ["key_1", "key-2", "KEY3"]),
            ("('key_.-;!)1!' was unexpected)", ["key_.-;!)1!"]),
        )
    )
    async def test_get_schema_failure_keys(self, msg, expected):
        """Test 1 or more keys are extracted correctly."""

        with (
            patch("subiquity.cloudinit.arun_command", new=Mock()),
            patch("subiquity.cloudinit.asyncio.wait_for") as wait_for_mock,
        ):
            wait_for_mock.return_value = CompletedProcess(
                args=[], returncode=1, stderr=msg
            )

            bad_keys = await get_unknown_keys()

        self.assertEqual(bad_keys, expected)

    @patch("subiquity.cloudinit.arun_command", new=Mock())
    @patch("subiquity.cloudinit.asyncio.wait_for")
    async def test_get_schema_failure_malformed(self, wait_for_mock):
        """Test graceful failure if output changes."""

        error_msg = "('key_1', 'key-2', 'KEY3', were unexpected)"

        wait_for_mock.return_value = CompletedProcess(
            args=[], returncode=1, stderr=error_msg
        )

        bad_keys = await get_unknown_keys()

        self.assertEqual(bad_keys, [])

    @patch("subiquity.cloudinit.arun_command", new=Mock())
    @patch("subiquity.cloudinit.asyncio.wait_for")
    async def test_no_schema_errors(self, wait_for_mock):
        wait_for_mock.return_value = CompletedProcess(args=[], returncode=0, stderr="")

        self.assertEqual(None, await validate_cloud_init_top_level_keys())

    @patch("subiquity.cloudinit.get_unknown_keys")
    async def test_validate_cloud_init_schema(self, sources_mock):
        mock_keys = ["key1", "key2"]
        sources_mock.return_value = mock_keys

        with self.assertRaises(CloudInitSchemaTopLevelKeyError) as ctx:
            await validate_cloud_init_top_level_keys()

        self.assertEqual(mock_keys, ctx.exception.keys)

    @patch("subiquity.cloudinit.arun_command", new=Mock())
    @patch("subiquity.cloudinit.asyncio.wait_for")
    @patch("subiquity.cloudinit.log")
    async def test_get_schema_warn_on_timeout(self, log_mock, wait_for_mock):
        wait_for_mock.side_effect = asyncio.TimeoutError()
        sources = await get_unknown_keys()
        log_mock.warning.assert_called()
        self.assertEqual([], sources)

    @parameterized.expand(
        (
            ("20.2", True),
            ("22.1", True),
            ("22.2", False),
            ("23.0", False),
        )
    )
    async def test_version_check_and_skip(self, version, should_skip):
        """Test that top-level key validation skipped on right versions.

        The "schema" subcommand, which the top-level key validation relies
        on, was added in cloud-init version 22.2. This test is to ensure
        that it's skipped on older releases.
        """
        with (
            patch("subiquity.cloudinit.get_unknown_keys") as keys_mock,
            patch("subiquity.cloudinit.cloud_init_version") as version_mock,
        ):
            version_mock.return_value = version

            if should_skip:
                await validate_cloud_init_top_level_keys()
                keys_mock.assert_not_called()

            else:
                keys_mock.return_value = []  # avoid raise condition
                await validate_cloud_init_top_level_keys()
                keys_mock.assert_called_once()


class TestCloudInitRandomStrings(SubiTestCase):
    def test_passwd_constraints(self):
        # password is 20 characters by default
        password = rand_user_password()
        self.assertEqual(len(password), 20)

        # password is requested length
        password = rand_user_password(pwlen=32)
        self.assertEqual(len(password), 32)

        # passwords contain valid chars
        # sample passwords
        for _i in range(100):
            password = rand_user_password()
            self.assertTrue(all(char in CLOUD_INIT_PW_SET for char in password))

    def test_rand_string_generation(self):
        # random string is 32 characters by default
        password = rand_password()
        self.assertEqual(len(password), 32)

        # password is requested length
        password = rand_password(strlen=20)
        self.assertEqual(len(password), 20)

        # password characters sampled from provided set
        choices = ["a"]
        self.assertEqual("a" * 32, rand_password(select_from=choices))


class TestCloudInitSchemaValidation(SubiTestCase):
    """Test cloud-init schema Validation."""

    @patch("subiquity.cloudinit.legacy_cloud_init_validation")
    @patch("subiquity.cloudinit.Path")
    @patch("subiquity.cloudinit.tempfile.TemporaryDirectory")
    async def test_config_dump(self, tempdir_mock, path_mock, legacy_validate_mock):
        """Test the config and source passed correctly."""
        test_config = {"mock key": "mock value"}
        validate_cloud_config_schema(test_config, "mock source")

        # Config is the same
        result_path = path_mock.return_value.__truediv__.return_value
        result_path.write_text.assert_called_with(yaml.dump(test_config))

        # Source is the same
        legacy_validate_mock.assert_called_with(str(result_path), "mock source")


@patch("subiquity.cloudinit.arun_command")
@patch("subiquity.cloudinit.system_scripts_env")
class TestCloudInitLegacyExtract(SubiTestCase):
    """Test subiquity-legacy-cloud-init-extract helper function."""

    @patch("subiquity.cloudinit.yaml.safe_load")
    async def test_called_with_correct_env(
        self,
        safe_load_mock,
        scripts_env_mock,
        arun_mock,
    ):
        """Test legacy script is called with system_scripts env."""
        mock_env = {"mock": "env"}
        scripts_env_mock.return_value = mock_env
        await legacy_cloud_init_extract()
        self.assertEqual(arun_mock.call_args.kwargs["env"], mock_env)

    async def test_read_stdout(
        self,
        scripts_env_mock,
        arun_mock,
    ):
        """Test reads yaml from stdout."""
        prog_output = {"cloud_cfg": {"some": "data"}, "installer_user_name": "pytest"}
        expected_cloud_cfg = prog_output["cloud_cfg"]
        expected_installer_user_name = prog_output["installer_user_name"]
        arun_mock.return_value.stdout = yaml.dump(prog_output)

        cloud_cfg, installer_user_name = await legacy_cloud_init_extract()
        self.assertEqual(cloud_cfg, expected_cloud_cfg)
        self.assertEqual(installer_user_name, expected_installer_user_name)

    async def test_useful_error(
        self,
        scripts_env_mock,
        arun_mock,
    ):
        """Test reports errors usefully."""
        arun_mock.side_effect = cpe = CalledProcessError(
            1, ["extract"], "stdout", "stderr"
        )

        with (
            self.assertRaises(CalledProcessError),
            patch("subiquity.cloudinit.log_process_streams") as log_mock,
        ):
            await legacy_cloud_init_extract()

        log_mock.assert_called_with(
            logging.DEBUG, cpe, "subiquity-legacy-cloud-init-extract"
        )


@patch("subiquity.cloudinit.run_command")
@patch("subiquity.cloudinit.system_scripts_env")
class TestCloudInitLegacyValidation(SubiTestCase):
    """Test subiquity-legacy-cloud-init-validation helper function."""

    def test_called_with_correct_env(
        self,
        scripts_env_mock,
        arun_mock,
    ):
        """Test legacy script is called with correct parameters and env."""
        prog_output = {"warnings": "", "errors": ""}
        arun_mock.return_value.stdout = yaml.dump(prog_output)

        mock_env = {"mock": "env"}
        scripts_env_mock.return_value = mock_env

        legacy_cloud_init_validation("mock_config", "mock source")

        scripts_env_mock.assert_called_once()
        arun_mock.assert_called_with(
            [
                "subiquity-legacy-cloud-init-validate",
                "--config",
                "mock_config",
                "--source",
                "mock source",
            ],
            env=mock_env,
            check=True,
        )

    def test_useful_cpe_error(
        self,
        scripts_env_mock,
        arun_mock,
    ):
        """Test reports CalledProcessError usefully."""
        arun_mock.side_effect = cpe = CalledProcessError(
            1, ["validate"], "stdout", "stderr"
        )

        with (
            self.assertRaises(CalledProcessError),
            patch("subiquity.cloudinit.log_process_streams") as log_mock,
        ):
            legacy_cloud_init_validation("", "")

        log_mock.assert_called_with(
            logging.DEBUG, cpe, "subiquity-legacy-cloud-init-validate"
        )

    def test_raise_schema_error(
        self,
        scripts_env_mock,
        arun_mock,
    ):
        """Test raise CloudInitSchemaValidationError on errors encountered."""
        prog_output = {"warnings": "", "errors": "bad config!"}
        arun_mock.return_value.stdout = yaml.dump(prog_output)

        with self.assertRaises(CloudInitSchemaValidationError):
            legacy_cloud_init_validation("", "")

    async def test_log_warnings(
        self,
        scripts_env_mock,
        arun_mock,
    ):
        """Test raise CloudInitSchemaValidationError on errors encountered."""
        prog_output = {"warnings": "deprecated key!", "errors": ""}
        arun_mock.return_value.stdout = yaml.dump(prog_output)

        with self.assertLogs("subiquity.cloudinit") as log_mock:
            legacy_cloud_init_validation("", "")

        self.assertIn("deprecated key!", log_mock.output[0])
