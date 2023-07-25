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

import unittest
from unittest.mock import AsyncMock, patch

from subiquity.server.contract_selection import (
    ContractSelection,
    UnknownError,
    UPCSExpiredError,
)


class TestContractSelection(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()

    async def test_init(self):
        with patch.object(
            ContractSelection, "_run_polling", return_value=None
        ) as run_polling:
            cs = ContractSelection(
                client=self.client,
                magic_token="magic",
                user_code="user-code",
                validity_seconds=200,
            )

        self.assertIs(cs.client, self.client)
        self.assertEqual(cs.magic_token, "magic")
        self.assertEqual(cs.user_code, "user-code")
        self.assertEqual(cs.validity_seconds, 200)
        self.assertIsNone(await cs.task)

        run_polling.assert_called_once_with()

    async def test_initiate_error(self):
        ret = {
            "errors": ["Initiate failed"],
            "result": "failure",
        }
        with patch.object(self.client.strategy, "magic_initiate_v1", return_value=ret):
            with self.assertRaises(UnknownError) as cm:
                await ContractSelection.initiate(self.client)
            self.assertIn("Initiate failed", cm.exception.errors)

    @patch.object(ContractSelection, "_run_polling", return_value=None)
    async def test_initiate_ok(self, run_polling):
        ret = {
            "result": "success",
            "data": {
                "attributes": {
                    "token": "magic-12345",
                    "user_code": "ABCDEF",
                    "expires_in": 200,
                },
            },
        }
        with patch.object(self.client.strategy, "magic_initiate_v1", return_value=ret):
            cs = await ContractSelection.initiate(self.client)

        self.assertEqual(cs.magic_token, "magic-12345")
        self.assertEqual(cs.user_code, "ABCDEF")

    @patch("asyncio.sleep")
    async def test_run_polling_errors(self, sleep):
        ret = {
            "result": "failure",
            "errors": [
                {
                    "title": "The magic attach token is invalid..",
                    "code": "magic-attach-token-error",
                },
            ],
        }
        with patch.object(ContractSelection, "_run_polling", return_value=None):
            cs = ContractSelection(
                client=self.client,
                magic_token="magic-token",
                user_code="ABCDEF",
                validity_seconds=200,
            )
        await cs.task

        self.client.strategy.scale_factor = 1
        with patch.object(self.client.strategy, "magic_wait_v1", return_value=ret):
            # 100 seconds elapsed, should be considered a timeout
            with patch("time.monotonic", side_effect=[100, 200]):
                with self.assertRaises(UPCSExpiredError):
                    await cs._run_polling()

            # 50 seconds elapsed, should be considered an unknown error
            with patch("time.monotonic", side_effect=[100, 150]):
                with self.assertRaises(UnknownError):
                    await cs._run_polling()

    @patch("asyncio.sleep")
    async def test_run_polling_ok(self, sleep):
        ret = {
            "result": "success",
            "data": {
                "attributes": {
                    "contract_token": "C12345257",
                },
            },
        }
        with patch.object(ContractSelection, "_run_polling", return_value=None):
            cs = ContractSelection(
                client=self.client,
                magic_token="magic-token",
                user_code="ABCDEF",
                validity_seconds=200,
            )
        await cs.task

        self.client.strategy.scale_factor = 1
        with patch.object(self.client.strategy, "magic_wait_v1", return_value=ret):
            self.assertEqual((await cs._run_polling()), "C12345257")
