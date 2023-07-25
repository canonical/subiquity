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
from unittest import mock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from subiquity.common.api.defs import Payload, allowed_before_start, api, path_parameter
from subiquity.common.api.server import (
    MissingImplementationError,
    SignatureMisatchError,
    bind,
    controller_for_request,
)
from subiquitycore.context import Context


class TestApp:
    def report_start_event(self, context, description):
        pass

    def report_finish_event(self, context, description, result):
        pass

    project = "test"


class ControllerBase:
    def __init__(self):
        self.context = Context.new(TestApp())
        self.app = mock.Mock()
        self.app.controllers_have_started = mock.MagicMock(return_value=True)


@contextlib.asynccontextmanager
async def makeTestClient(api, impl, middlewares=()):
    app = web.Application(middlewares=middlewares)
    bind(app.router, api, impl)
    async with TestClient(TestServer(app)) as client:
        yield client


class TestBind(unittest.IsolatedAsyncioTestCase):
    async def assertResponse(self, coro, value):
        resp = await coro
        if resp.headers.get("x-error-msg"):
            raise Exception(
                resp.headers["x-error-type"] + ": " + resp.headers["x-error-msg"]
            )
        self.assertEqual(resp.status, 200)
        self.assertEqual(await resp.json(), value)

    async def test_simple(self):
        @api
        class API:
            def GET() -> str:
                ...

        class Impl(ControllerBase):
            async def GET(self) -> str:
                return "value"

        async with makeTestClient(API, Impl()) as client:
            await self.assertResponse(client.get("/"), "value")

    async def test_nested(self):
        @api
        class API:
            class endpoint:
                class nested:
                    def get():
                        ...

        class Impl(ControllerBase):
            async def nested_get(self, request, context):
                return "nested"

        async with makeTestClient(API.endpoint, Impl()) as client:
            await self.assertResponse(client.get("/endpoint/nested"), "nested")

    async def test_args(self):
        @api
        class API:
            def GET(arg: str):
                ...

        class Impl(ControllerBase):
            async def GET(self, arg: str):
                return arg

        async with makeTestClient(API, Impl()) as client:
            await self.assertResponse(client.get('/?arg="whut"'), "whut")

    async def test_missing_argument(self):
        @api
        class API:
            def GET(arg: str):
                ...

        class Impl(ControllerBase):
            async def GET(self, arg: str):
                return arg

        async with makeTestClient(API, Impl()) as client:
            resp = await client.get("/")
            self.assertEqual(resp.status, 500)
            self.assertEqual(resp.headers["x-status"], "error")
            self.assertEqual(resp.headers["x-error-type"], "TypeError")
            self.assertEqual(
                resp.headers["x-error-msg"], 'missing required argument "arg"'
            )

    async def test_error(self):
        @api
        class API:
            def GET():
                ...

        class Impl(ControllerBase):
            async def GET(self):
                return 1 / 0

        async with makeTestClient(API, Impl()) as client:
            resp = await client.get("/")
            self.assertEqual(resp.status, 500)
            self.assertEqual(resp.headers["x-status"], "error")
            self.assertEqual(resp.headers["x-error-type"], "ZeroDivisionError")

    async def test_post(self):
        @api
        class API:
            def POST(data: Payload[str]) -> str:
                ...

        class Impl(ControllerBase):
            async def POST(self, data: str) -> str:
                return data

        async with makeTestClient(API, Impl()) as client:
            await self.assertResponse(client.post("/", json="value"), "value")

    def test_missing_method(self):
        @api
        class API:
            def GET(arg: str):
                ...

        class Impl(ControllerBase):
            pass

        app = web.Application()
        with self.assertRaises(MissingImplementationError) as cm:
            bind(app.router, API, Impl())
        self.assertEqual(cm.exception.methname, "GET")

    def test_signature_checking(self):
        @api
        class API:
            def GET(arg: str):
                ...

        class Impl(ControllerBase):
            async def GET(self, arg: int):
                return arg

        app = web.Application()
        with self.assertRaises(SignatureMisatchError) as cm:
            bind(app.router, API, Impl())
        self.assertEqual(cm.exception.methname, "API.GET")

    async def test_middleware(self):
        @web.middleware
        async def middleware(request, handler):
            resp = await handler(request)
            exc = resp.get("exception")
            if resp.get("exception") is not None:
                resp.headers["x-error-type"] = type(exc).__name__
            return resp

        @api
        class API:
            def GET() -> str:
                ...

        class Impl(ControllerBase):
            async def GET(self) -> str:
                return 1 / 0

        async with makeTestClient(API, Impl(), middlewares=[middleware]) as client:
            resp = await client.get("/")
            self.assertEqual(resp.headers["x-error-type"], "ZeroDivisionError")

    async def test_controller_for_request(self):
        seen_controller = None

        @web.middleware
        async def middleware(request, handler):
            nonlocal seen_controller
            seen_controller = await controller_for_request(request)
            return await handler(request)

        @api
        class API:
            class meth:
                def GET() -> str:
                    ...

        class Impl(ControllerBase):
            async def GET(self) -> str:
                return ""

        impl = Impl()

        async with makeTestClient(API.meth, impl, middlewares=[middleware]) as client:
            resp = await client.get("/meth")
            self.assertEqual(await resp.json(), "")

        self.assertIs(impl, seen_controller)

    async def test_serialize_query_args(self):
        @api
        class API:
            serialize_query_args = False

            def GET(arg: str) -> str:
                ...

            class meth:
                def GET(arg: str) -> str:
                    ...

                class more:
                    serialize_query_args = True

                    def GET(arg: str) -> str:
                        ...

        class Impl(ControllerBase):
            async def GET(self, arg: str) -> str:
                return arg

            async def meth_GET(self, arg: str) -> str:
                return arg

            async def meth_more_GET(self, arg: str) -> str:
                return arg

        async with makeTestClient(API, Impl()) as client:
            await self.assertResponse(client.get("/?arg=whut"), "whut")
            await self.assertResponse(client.get("/meth?arg=whut"), "whut")
            await self.assertResponse(client.get('/meth/more?arg="whut"'), "whut")

    async def test_path_parameters(self):
        @api
        class API:
            @path_parameter
            class param:
                def GET(arg: int):
                    ...

        class Impl(ControllerBase):
            async def param_GET(self, param: str, arg: int):
                return param + str(arg)

        async with makeTestClient(API, Impl()) as client:
            await self.assertResponse(client.get("/value?arg=2"), "value2")

    async def test_early_connect_ok(self):
        @api
        class API:
            class can_be_used_early:
                @allowed_before_start
                def GET():
                    ...

        class Impl(ControllerBase):
            def __init__(self):
                super().__init__()
                self.app.controllers_have_started = mock.AsyncMock()
                self.app.controllers_have_started.is_set = mock.Mock(return_value=False)

            async def can_be_used_early_GET(self):
                pass

        impl = Impl()
        async with makeTestClient(API, impl) as client:
            await client.get("/can_be_used_early")
            impl.app.controllers_have_started.wait.assert_not_called()

    async def test_early_connect_wait(self):
        @api
        class API:
            class must_not_be_used_early:
                def GET():
                    ...

        class Impl(ControllerBase):
            def __init__(self):
                super().__init__()
                self.app.controllers_have_started = mock.AsyncMock()
                self.app.controllers_have_started.is_set = mock.Mock(return_value=False)

            async def must_not_be_used_early_GET(self):
                pass

        impl = Impl()
        async with makeTestClient(API, impl) as client:
            await client.get("/must_not_be_used_early")
            impl.app.controllers_have_started.wait.assert_called_once()
