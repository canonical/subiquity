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
import functools
import unittest

import aiohttp
import attr
from aiohttp import web

from subiquity.common.api.client import make_client
from subiquity.common.api.defs import (
    MultiplePathParameters,
    Payload,
    api,
    path_parameter,
)

from .test_server import ControllerBase, makeTestClient


def make_request(client, method, path, *, params, json, raise_for_status):
    return client.request(method, path, params=params, json=json)


@contextlib.asynccontextmanager
async def makeE2EClient(api, impl, *, middlewares=(), make_request=make_request):
    async with makeTestClient(api, impl, middlewares=middlewares) as client:
        mr = functools.partial(make_request, client)
        yield make_client(api, mr)


class TestEndToEnd(unittest.IsolatedAsyncioTestCase):
    async def test_simple(self):
        @api
        class API:
            def GET() -> str: ...

        class Impl(ControllerBase):
            async def GET(self) -> str:
                return "value"

        async with makeE2EClient(API, Impl()) as client:
            self.assertEqual(await client.GET(), "value")

    async def test_nested(self):
        @api
        class API:
            class endpoint:
                class nested:
                    def GET() -> str: ...

        class Impl(ControllerBase):
            async def endpoint_nested_GET(self) -> str:
                return "value"

        async with makeE2EClient(API, Impl()) as client:
            self.assertEqual(await client.endpoint.nested.GET(), "value")

    async def test_args(self):
        @api
        class API:
            def GET(arg1: str, arg2: str) -> str: ...

        class Impl(ControllerBase):
            async def GET(self, arg1: str, arg2: str) -> str:
                return "{}+{}".format(arg1, arg2)

        async with makeE2EClient(API, Impl()) as client:
            self.assertEqual(await client.GET(arg1="A", arg2="B"), "A+B")

    async def test_path_args(self):
        @api
        class API:
            @path_parameter
            class param1:
                @path_parameter
                class param2:
                    def GET(arg1: str, arg2: str) -> str: ...

        class Impl(ControllerBase):
            async def param1_param2_GET(
                self, param1: str, param2: str, arg1: str, arg2: str
            ) -> str:
                return "{}+{}+{}+{}".format(param1, param2, arg1, arg2)

        async with makeE2EClient(API, Impl()) as client:
            self.assertEqual(await client["1"]["2"].GET(arg1="A", arg2="B"), "1+2+A+B")

    def test_only_one_path_parameter(self):
        class API:
            @path_parameter
            class param1:
                def GET(arg: str) -> str: ...

            @path_parameter
            class param2:
                def GET(arg: str) -> str: ...

        with self.assertRaises(MultiplePathParameters):
            api(API)

    async def test_defaults(self):
        @api
        class API:
            def GET(arg1: str = "arg1", arg2: str = "arg2") -> str: ...

        class Impl(ControllerBase):
            async def GET(self, arg1: str = "arg1", arg2: str = "arg2") -> str:
                return "{}+{}".format(arg1, arg2)

        async with makeE2EClient(API, Impl()) as client:
            self.assertEqual(await client.GET(arg1="A", arg2="B"), "A+B")
            self.assertEqual(await client.GET(arg1="A"), "A+arg2")
            self.assertEqual(await client.GET(arg2="B"), "arg1+B")

    async def test_post(self):
        @api
        class API:
            def POST(data: Payload[dict]) -> str: ...

        class Impl(ControllerBase):
            async def POST(self, data: dict) -> str:
                return data["key"]

        async with makeE2EClient(API, Impl()) as client:
            self.assertEqual(await client.POST({"key": "value"}), "value")

    async def test_typed(self):
        @attr.s(auto_attribs=True)
        class In:
            val: int

        @attr.s(auto_attribs=True)
        class Out:
            doubled: int

        @api
        class API:
            class doubler:
                def POST(data: In) -> Out: ...

        class Impl(ControllerBase):
            async def doubler_POST(self, data: In) -> Out:
                return Out(doubled=data.val * 2)

        async with makeE2EClient(API, Impl()) as client:
            out = await client.doubler.POST(In(3))
            self.assertEqual(out.doubled, 6)

    async def test_middleware(self):
        @api
        class API:
            def GET() -> int: ...

        class Impl(ControllerBase):
            async def GET(self) -> int:
                return 1 / 0

        @web.middleware
        async def middleware(request, handler):
            return web.Response(status=200, headers={"x-status": "skip"})

        class Skip(Exception):
            pass

        @contextlib.asynccontextmanager
        async def custom_make_request(
            client, method, path, *, params, json, raise_for_status
        ):
            async with make_request(
                client,
                method,
                path,
                params=params,
                json=json,
                raise_for_status=raise_for_status,
            ) as resp:
                if resp.headers.get("x-status") == "skip":
                    raise Skip
                yield resp

        async with makeE2EClient(
            API, Impl(), middlewares=[middleware], make_request=custom_make_request
        ) as client:
            with self.assertRaises(Skip):
                await client.GET()

    async def test_error(self):
        @api
        class API:
            class good:
                def GET(x: int) -> int: ...

            class bad:
                def GET(x: int) -> int: ...

        class Impl(ControllerBase):
            async def good_GET(self, x: int) -> int:
                return x + 1

            async def bad_GET(self, x: int) -> int:
                raise Exception("baz")

        async with makeE2EClient(API, Impl()) as client:
            r = await client.good.GET(2)
            self.assertEqual(r, 3)
            with self.assertRaises(aiohttp.ClientResponseError):
                await client.bad.GET(2)

    async def test_error_middleware(self):
        @api
        class API:
            class good:
                def GET(x: int) -> int: ...

            class bad:
                def GET(x: int) -> int: ...

        class Impl(ControllerBase):
            async def good_GET(self, x: int) -> int:
                return x + 1

            async def bad_GET(self, x: int) -> int:
                1 / 0

        @web.middleware
        async def middleware(request, handler):
            resp = await handler(request)
            if resp.get("exception"):
                resp.headers["x-status"] = "ERROR"
            return resp

        class Abort(Exception):
            pass

        @contextlib.asynccontextmanager
        async def custom_make_request(
            client, method, path, *, params, json, raise_for_status
        ):
            async with make_request(
                client,
                method,
                path,
                params=params,
                json=json,
                raise_for_status=raise_for_status,
            ) as resp:
                if resp.headers.get("x-status") == "ERROR":
                    raise Abort
                yield resp

        async with makeE2EClient(
            API, Impl(), middlewares=[middleware], make_request=custom_make_request
        ) as client:
            r = await client.good.GET(2)
            self.assertEqual(r, 3)
            with self.assertRaises(Abort):
                await client.bad.GET(2)
