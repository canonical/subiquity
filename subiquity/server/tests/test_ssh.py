# Copyright 2023 Canonical, Ltd.
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
from subprocess import CalledProcessError, CompletedProcess
from unittest import mock

from subiquity.common.types import SSHFetchIdStatus
from subiquity.server.ssh import DryRunSSHKeyFetcher, SSHFetchError, SSHKeyFetcher
from subiquitycore.tests.mocks import make_app


class TestSSHKeyFetcher(unittest.IsolatedAsyncioTestCase):
    arun_command_sym = "subiquity.server.ssh.arun_command"

    def setUp(self):
        self.fetcher = SSHKeyFetcher(make_app())

    async def test_fetch_keys_for_id_one_key_ok(self):
        with mock.patch(self.arun_command_sym) as mock_arun:
            mock_arun.return_value = CompletedProcess([], 0)
            mock_arun.return_value.stdout = """
ssh-rsa AAAAC3NzaC1lZ test@gh/335797 # ssh-import-id gh:test
"""
            keys = await self.fetcher.fetch_keys_for_id(user_id="gh:test")
        self.assertEqual(
            keys,
            [
                "ssh-rsa AAAAC3NzaC1lZ test@gh/335797 # ssh-import-id gh:test",
            ],
        )

    async def test_fetch_keys_for_id_two_key_ok(self):
        with mock.patch(self.arun_command_sym) as mock_arun:
            mock_arun.return_value = CompletedProcess([], 0)
            mock_arun.return_value.stdout = """\
ssh-rsa AAAAC3NzaC1lZ test@host # ssh-import-id lp:test

ssh-ed25519 AAAAAC3N test@host # ssh-import-id lp:test
"""
            keys = await self.fetcher.fetch_keys_for_id(user_id="lp:test")
        self.assertEqual(
            keys,
            [
                "ssh-rsa AAAAC3NzaC1lZ test@host # ssh-import-id lp:test",
                "ssh-ed25519 AAAAAC3N test@host # ssh-import-id lp:test",
            ],
        )

    async def test_fetch_keys_for_id_error(self):
        with mock.patch(self.arun_command_sym) as mock_arun:
            stderr = """\
2022-11-22 14:00:12,336 INFO [0] SSH keys [Authorized]
2022-11-22 14:00:12,337 ERROR No matching keys found for [lp:test2]
"""
            mock_arun.side_effect = CalledProcessError(1, [], None, stderr)
            with self.assertRaises(SSHFetchError) as cm:
                await self.fetcher.fetch_keys_for_id(user_id="lp:test2")

            self.assertEqual(cm.exception.reason, stderr)
            self.assertEqual(cm.exception.status, SSHFetchIdStatus.IMPORT_ERROR)

    async def test_gen_fingerprint_for_key_ok(self):
        with mock.patch(self.arun_command_sym) as mock_arun:
            mock_arun.return_value = CompletedProcess([], 0)
            mock_arun.return_value.stdout = """\
256 SHA256:rIR9UVRKspl7+KF75s test@host # ssh-import-id lp:test (ED25519)
"""
            fp = await self.fetcher.gen_fingerprint_for_key(
                "ssh-ed25519 AAAAAC3N test@host # ssh-import-id lp:test"
            )

            self.assertEqual(
                fp,
                """\
256 SHA256:rIR9UVRKspl7+KF75s test@host # ssh-import-id lp:test (ED25519)\
""",
            )

    async def test_gen_fingerprint_for_key_error(self):
        stderr = "(stdin) is not a public key file.\n"
        with mock.patch(self.arun_command_sym) as mock_arun:
            mock_arun.side_effect = CalledProcessError(1, [], None, stderr)
            with self.assertRaises(SSHFetchError) as cm:
                await self.fetcher.gen_fingerprint_for_key(
                    "ssh-nsa AAAAAC3N test@host # ssh-import-id lp:test"
                )

            self.assertEqual(cm.exception.reason, stderr)
            self.assertEqual(cm.exception.status, SSHFetchIdStatus.FINGERPRINT_ERROR)


class TestDryRunSSHKeyFetcher(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fetcher = DryRunSSHKeyFetcher(make_app())

    async def test_fetch_keys_fake_success(self):
        result = await self.fetcher.fetch_keys_fake_success("lp:test")
        expected = [
            """\
ssh-ed25519\
 AAAAC3NzaC1lZDI1NTE5AAAAIMM/qhS3hS3+IjpJBYXZWCqPKPH9Zag8QYbS548iEjoZ\
 test@earth # ssh-import-id lp:test"""
        ]
        self.assertEqual(result, expected)

    async def test_fetch_keys_fake_failure(self):
        with self.assertRaises(SSHFetchError):
            await self.fetcher.fetch_keys_fake_failure("lp:test")
