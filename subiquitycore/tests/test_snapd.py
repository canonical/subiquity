# Copyright 2025 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import unittest
from unittest.mock import Mock

from subiquitycore.snapd import FakeSnapdConnection, _FakeMemoryResponse


class TestFakeSnapdConnection(unittest.TestCase):
    def setUp(self):
        self.snapd = FakeSnapdConnection(Mock(), Mock(), Mock())

    def test__fake_entropy__pin_bad(self):
        expected = _FakeMemoryResponse(
            {
                "type": "error",
                "status": "Bad Request",
                "status-code": 400,
                "result": {
                    "value": {
                        "entropy-bits": 3,
                        "min-entropy-bits": 4,
                        "optimal-entropy-bits": 6,
                        "reasons": ["low-entropy"],
                    },
                    "message": "did not pass quality checks",
                    "kind": "invalid-pin",
                },
            }
        )
        self.assertEqual(
            expected, self.snapd._fake_entropy({"action": "check-pin", "pin": "123"})
        )

    def test__fake_entropy__pin_good(self):
        expected = _FakeMemoryResponse(
            {
                "type": "sync",
                "status": "OK",
                "status-code": 200,
                "result": {
                    "entropy-bits": 5,
                    "min-entropy-bits": 4,
                    "optimal-entropy-bits": 6,
                },
            }
        )
        self.assertEqual(
            expected, self.snapd._fake_entropy({"action": "check-pin", "pin": "12345"})
        )

    def test__fake_entropy__passphrase_bad(self):
        expected = _FakeMemoryResponse(
            {
                "type": "error",
                "status": "Bad Request",
                "status-code": 400,
                "result": {
                    "value": {
                        "entropy-bits": 3,
                        "min-entropy-bits": 8,
                        "optimal-entropy-bits": 10,
                        "reasons": ["low-entropy"],
                    },
                    "message": "did not pass quality checks",
                    "kind": "invalid-passphrase",
                },
            }
        )
        self.assertEqual(
            expected,
            self.snapd._fake_entropy(
                {"action": "check-passphrase", "passphrase": "abc"}
            ),
        )

    def test__fake_entropy__passphrase_good(self):
        expected = _FakeMemoryResponse(
            {
                "type": "sync",
                "status": "OK",
                "status-code": 200,
                "result": {
                    "entropy-bits": 12,
                    "min-entropy-bits": 8,
                    "optimal-entropy-bits": 10,
                },
            }
        )
        self.assertEqual(
            expected,
            self.snapd._fake_entropy(
                {"action": "check-passphrase", "passphrase": "abcdefghijkl"}
            ),
        )
