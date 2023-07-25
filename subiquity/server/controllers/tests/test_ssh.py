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

import unittest
from unittest import mock

from subiquity.common.types import SSHFetchIdStatus, SSHIdentity
from subiquity.server.controllers.ssh import (
    SSHController,
    SSHFetchError,
    SSHFetchIdResponse,
)
from subiquitycore.tests.mocks import make_app


class TestSSHController(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.controller = SSHController(make_app())

    async def test_fetch_id_GET_ok(self):
        key = "ssh-rsa AAAAA[..] user@host # ssh-import-id lp:user"
        mock_fetch_keys = mock.patch.object(
            self.controller.fetcher, "fetch_keys_for_id", return_value=[key]
        )

        fp = "256 SHA256:rIR9[..] user@host # ssh-import-id lp:user (ED25519)"
        mock_gen_fingerprint = mock.patch.object(
            self.controller.fetcher, "gen_fingerprint_for_key", return_value=fp
        )

        with mock_fetch_keys, mock_gen_fingerprint:
            response = await self.controller.fetch_id_GET(user_id="lp:user")

            self.assertIsInstance(response, SSHFetchIdResponse)
            self.assertEqual(response.status, SSHFetchIdStatus.OK)
            self.assertEqual(
                response.identities,
                [
                    SSHIdentity(
                        key_type="ssh-rsa",
                        key="AAAAA[..]",
                        key_comment="user@host # ssh-import-id lp:user",
                        key_fingerprint="256 SHA256:rIR9[..] user@host  (ED25519)",
                    )
                ],
            )
            self.assertIsNone(response.error)

    async def test_fetch_id_GET_import_error(self):
        stderr = "ERROR No matching keys found for [lp=test2]\n"

        mock_fetch_keys = mock.patch.object(
            self.controller.fetcher,
            "fetch_keys_for_id",
            side_effect=SSHFetchError(
                status=SSHFetchIdStatus.IMPORT_ERROR, reason=stderr
            ),
        )

        with mock_fetch_keys:
            response = await self.controller.fetch_id_GET(user_id="test2")

            self.assertEqual(response.status, SSHFetchIdStatus.IMPORT_ERROR)
            self.assertEqual(response.error, stderr)
            self.assertIsNone(response.identities)

    async def test_fetch_id_GET_fingerprint_error(self):
        key = "ssh-rsa AAAAA[..] user@host # ssh-import-id lp:user"
        mock_fetch_keys = mock.patch.object(
            self.controller.fetcher, "fetch_keys_for_id", return_value=[key]
        )

        stderr = "(stdin) is not a public key file\n"

        mock_gen_fingerprint = mock.patch.object(
            self.controller.fetcher,
            "gen_fingerprint_for_key",
            side_effect=SSHFetchError(
                status=SSHFetchIdStatus.FINGERPRINT_ERROR, reason=stderr
            ),
        )

        with mock_fetch_keys, mock_gen_fingerprint:
            response = await self.controller.fetch_id_GET(user_id="test2")

            self.assertEqual(response.status, SSHFetchIdStatus.FINGERPRINT_ERROR)
            self.assertEqual(response.error, stderr)
            self.assertIsNone(response.identities)
