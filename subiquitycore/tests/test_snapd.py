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

import json
import os
import shutil
import tempfile
import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import requests

from subiquitycore.snapd import (
    AsyncSnapd,
    FakeSnapdConnection,
    MemoryResponseSet,
    _FakeFileResponse,
    _FakeMemoryResponse,
    requests_response_from_json,
)
from subiquitycore.tests import SubiTestCase


class TestFakeSnapdConnection(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test-snapd-")
        self.addCleanup(shutil.rmtree, self.tmpdir)
        os.makedirs(os.path.join(self.tmpdir, "run", "subiquity"))
        self.snapd = FakeSnapdConnection(self.tmpdir, 1000, self.tmpdir)

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

    def test_get_raises_on_error_no_raise_on_success(self):
        self.snapd.response_sets = {
            "v2-systems": MemoryResponseSet(
                [
                    {"status-code": 200, "status": "OK", "result": {"managed": True}},
                    {"status-code": 500, "status": "Internal Server Error"},
                ]
            )
        }
        self.snapd.get("v2/systems").raise_for_status()
        with self.assertRaises(requests.exceptions.HTTPError):
            self.snapd.get("v2/systems").raise_for_status()

    def test_post_entropy_and_refresh(self):
        # _fake_entropy returns status-code 400 for short pins, 200 for good ones;
        # refresh always returns 200. Both now go through as_response().
        with self.assertRaises(requests.exceptions.HTTPError):
            self.snapd.post(
                "v2/systems/x", {"action": "check-pin", "pin": "12"}
            ).raise_for_status()
        self.snapd.post(
            "v2/systems/x", {"action": "check-pin", "pin": "12345"}
        ).raise_for_status()
        self.snapd.post("v2/snaps/subiquity", {"action": "refresh"}).raise_for_status()


class TestRequestsResponseFromJson(unittest.TestCase):
    """requests_response_from_json builds a real requests.Response so
    raise_for_status() can raise on 4xx/5xx."""

    def test_status_code_content_type_and_roundtrip(self):
        body = {"status-code": 200, "status": "OK", "result": {"ok": True}}
        resp = requests_response_from_json(json.dumps(body))
        self.assertEqual(200, resp.status_code)
        self.assertEqual("OK", resp.reason)
        self.assertEqual("utf-8", resp.encoding)
        self.assertEqual("application/json", resp.headers["Content-Type"])
        self.assertEqual(body, resp.json())
        self.assertEqual(json.dumps(body), resp.text)

    def test_raise_for_status_raises_on_4xx_5xx_exposing_response(self):
        # 2xx must not raise; 4xx and 5xx must raise, and the raised
        # HTTPError must expose the originating response (production handlers
        # read the body via .response).
        for code in (200, 201, 204):
            requests_response_from_json(
                json.dumps({"status-code": code, "status": "OK"})
            ).raise_for_status()
        for code, status in ((400, "Bad Request"), (500, "Server Error")):
            resp = requests_response_from_json(
                json.dumps({"status-code": code, "status": status})
            )
            with self.assertRaises(requests.exceptions.HTTPError) as ctx:
                resp.raise_for_status()
            self.assertIs(resp, ctx.exception.response)


class TestFakeMemoryResponse(unittest.TestCase):
    """_FakeMemoryResponse.as_response() passes json.dumps(data) to
    requests_response_from_json."""

    def test_as_response(self):
        data = {"status-code": 200, "status": "OK", "result": {"value": 42}}
        with patch("subiquitycore.snapd.requests_response_from_json") as m:
            _FakeMemoryResponse(data).as_response()
        m.assert_called_once_with(json.dumps(data))


class TestFakeFileResponse(SubiTestCase):
    """_FakeFileResponse.as_response() passes file contents to
    requests_response_from_json."""

    def test_as_response(self):
        raw = '{"status-code": 500, "status": "Internal Server Error"}'
        path = self.tmp_path("response.json")
        with open(path, "w") as fh:
            fh.write(raw)
        with patch("subiquitycore.snapd.requests_response_from_json") as m:
            _FakeFileResponse(path).as_response()
        m.assert_called_once_with(raw)


class TestAsyncSnapdRaiseOnStatus(IsolatedAsyncioTestCase):
    """AsyncSnapd.get/post raise on error status by default."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test-snapd-")
        self.addCleanup(shutil.rmtree, self.tmpdir)
        os.makedirs(os.path.join(self.tmpdir, "run", "subiquity"))
        self.connection = FakeSnapdConnection(self.tmpdir, 1000, self.tmpdir)
        self.snapd = AsyncSnapd(self.connection)

    async def test_get_raises_on_error_returns_json_on_success(self):
        self.connection.response_sets = {
            "v2-systems": MemoryResponseSet(
                [
                    {"status-code": 200, "status": "OK", "result": {"managed": True}},
                    {"status-code": 500, "status": "Internal Server Error"},
                ]
            )
        }
        result = await self.snapd.get("v2/systems")
        self.assertEqual({"managed": True}, result["result"])
        with self.assertRaises(requests.exceptions.HTTPError):
            await self.snapd.get("v2/systems")

    async def test_post_raises_on_error_returns_json_on_success(self):
        with self.assertRaises(requests.exceptions.HTTPError):
            await self.snapd.post("v2/systems/x", {"action": "check-pin", "pin": "12"})
        result = await self.snapd.post("v2/snaps/subiquity", {"action": "refresh"})
        self.assertEqual(200, result["status-code"])

    async def test_no_raise_when_raise_for_status_false(self):
        self.connection.response_sets = {
            "v2-systems": MemoryResponseSet(
                [{"status-code": 500, "status": "Internal Server Error"}]
            )
        }
        # raise_for_status=False suppresses the raise and returns the parsed
        # error body instead.
        self.assertEqual(
            500,
            (await self.snapd.get("v2/systems", raise_for_status=False))["status-code"],
        )
        self.assertEqual(
            400,
            (
                await self.snapd.post(
                    "v2/systems/x",
                    {"action": "check-pin", "pin": "12"},
                    raise_for_status=False,
                )
            )["status-code"],
        )
