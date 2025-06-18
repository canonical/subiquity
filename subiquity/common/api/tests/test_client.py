# Copyright 2020 Canonical, Ltd.
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
import unittest

from subiquity.common.api.client import make_client
from subiquity.common.api.defs import InvalidQueryArgs, Payload, api, path_parameter


def extract(c):
    try:
        c.__await__().send(None)
    except StopIteration as s:
        return s.value
    else:
        raise AssertionError("coroutine not done")


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    async def json(self):
        return self.data


class TestClient(unittest.TestCase):
    def test_simple(self):
        @api
        class API:
            class endpoint:
                def GET() -> str: ...

                def POST(data: Payload[str]) -> None: ...

        @contextlib.asynccontextmanager
        async def make_request(method, path, *, params, json, raise_for_status):
            requests.append((method, path, params, json))
            if method == "GET":
                v = "value"
            else:
                v = None
            yield FakeResponse(v)

        client = make_client(API, make_request)

        requests = []
        r = extract(client.endpoint.GET())
        self.assertEqual(r, "value")
        self.assertEqual(requests, [("GET", "/endpoint", {}, None)])

        requests = []
        r = extract(client.endpoint.POST("value"))
        self.assertEqual(r, None)
        self.assertEqual(requests, [("POST", "/endpoint", {}, "value")])

    def test_args(self):
        @api
        class API:
            def GET(arg: str) -> str: ...

        @contextlib.asynccontextmanager
        async def make_request(method, path, *, params, json, raise_for_status):
            requests.append((method, path, params, json))
            yield FakeResponse(params["arg"])

        client = make_client(API, make_request)

        requests = []
        r = extract(client.GET(arg="v"))
        self.assertEqual(r, '"v"')
        self.assertEqual(requests, [("GET", "/", {"arg": '"v"'}, None)])

    def test_path_params(self):
        @api
        class API:
            @path_parameter
            class param:
                def GET(arg: str) -> str: ...

        @contextlib.asynccontextmanager
        async def make_request(method, path, *, params, json, raise_for_status):
            requests.append((method, path, params, json))
            yield FakeResponse(params["arg"])

        client = make_client(API, make_request)

        requests = []
        r = extract(client["foo"].GET(arg="v"))
        self.assertEqual(r, '"v"')
        self.assertEqual(requests, [("GET", "/foo", {"arg": '"v"'}, None)])

    def test_serialize_query_args(self):
        @api
        class API:
            serialize_query_args = False

            def GET(arg: str) -> str: ...

            class meth:
                def GET(arg: str, payload: Payload[int]) -> str: ...

                class more:
                    serialize_query_args = True

                    def GET(arg: str) -> str: ...

        @contextlib.asynccontextmanager
        async def make_request(method, path, *, params, json, raise_for_status):
            requests.append((method, path, params, json))
            yield FakeResponse(params["arg"])

        client = make_client(API, make_request)

        requests = []
        extract(client.GET(arg="v"))
        extract(client.meth.GET(arg="v", payload=1))
        extract(client.meth.more.GET(arg="v"))
        self.assertEqual(
            requests,
            [
                ("GET", "/", {"arg": "v"}, None),
                ("GET", "/meth", {"arg": "v"}, 1),
                ("GET", "/meth/more", {"arg": '"v"'}, None),
            ],
        )

        class API2:
            serialize_query_args = False

            def GET(arg: int) -> str: ...

        with self.assertRaises(InvalidQueryArgs):
            api(API2)
