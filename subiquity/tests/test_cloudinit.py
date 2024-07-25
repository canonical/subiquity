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
from subprocess import CompletedProcess
from unittest import skipIf
from unittest.mock import Mock, patch

from subiquity.cloudinit import (
    CLOUD_INIT_PW_SET,
    CloudInitSchemaValidationError,
    cloud_init_status_wait,
    cloud_init_version,
    get_schema_failure_keys,
    rand_password,
    rand_user_password,
    read_json_extended_status,
    read_legacy_status,
    supports_format_json,
    supports_recoverable_errors,
    validate_cloud_init_schema,
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


class TestCloudInitSchemaValidation(SubiTestCase):
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

            bad_keys = await get_schema_failure_keys()

        self.assertEqual(bad_keys, expected)

    @patch("subiquity.cloudinit.arun_command", new=Mock())
    @patch("subiquity.cloudinit.asyncio.wait_for")
    async def test_get_schema_failure_malformed(self, wait_for_mock):
        """Test graceful failure if output changes."""

        error_msg = "('key_1', 'key-2', 'KEY3', were unexpected)"

        wait_for_mock.return_value = CompletedProcess(
            args=[], returncode=1, stderr=error_msg
        )

        bad_keys = await get_schema_failure_keys()

        self.assertEqual(bad_keys, [])

    @patch("subiquity.cloudinit.arun_command", new=Mock())
    @patch("subiquity.cloudinit.asyncio.wait_for")
    async def test_no_schema_errors(self, wait_for_mock):
        wait_for_mock.return_value = CompletedProcess(args=[], returncode=0, stderr="")

        self.assertEqual(None, await validate_cloud_init_schema())

    @patch("subiquity.cloudinit.get_schema_failure_keys")
    async def test_validate_cloud_init_schema(self, sources_mock):
        mock_keys = ["key1", "key2"]
        sources_mock.return_value = mock_keys

        with self.assertRaises(CloudInitSchemaValidationError) as ctx:
            await validate_cloud_init_schema()

        self.assertEqual(mock_keys, ctx.exception.keys)

    @patch("subiquity.cloudinit.arun_command", new=Mock())
    @patch("subiquity.cloudinit.asyncio.wait_for")
    @patch("subiquity.cloudinit.log")
    async def test_get_schema_warn_on_timeout(self, log_mock, wait_for_mock):
        wait_for_mock.side_effect = asyncio.TimeoutError()
        sources = await get_schema_failure_keys()
        log_mock.warning.assert_called()
        self.assertEqual([], sources)


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
