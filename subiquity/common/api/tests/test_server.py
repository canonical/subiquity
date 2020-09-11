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

import asyncio
import unittest

from aiohttp.test_utils import TestClient, TestServer
from aiohttp import web

from subiquitycore.context import Context
from subiquitycore import contextlib38

from subiquity.common.api.defs import api, Payload
from subiquity.common.api.server import (
    bind,
    controller_for_request,
    MissingImplementationError,
    SignatureMisatchError,
    )


def run_coro(coro):
    asyncio.get_event_loop().run_until_complete(coro)


class TestApp:

    def report_start_event(self, context, description):
        pass

    def report_finish_event(self, context, description, result):
        pass

    project = 'test'


class TestControllerBase:

    def __init__(self):
        self.context = Context.new(TestApp())


@contextlib38.asynccontextmanager
async def makeTestClient(api, impl, middlewares=()):
    app = web.Application(middlewares=middlewares)
    bind(app.router, api, impl)
    async with TestClient(TestServer(app)) as client:
        yield client


class TestBind(unittest.TestCase):

    async def assertResponse(self, coro, value):
        resp = await coro
        self.assertEqual(resp.status, 200)
        self.assertEqual(await resp.json(), value)

    def test_simple(self):
        @api
        class API:
            def GET() -> str: ...

        class Impl(TestControllerBase):
            async def GET(self) -> str:
                return 'value'

        async def run():
            async with makeTestClient(API, Impl()) as client:
                await self.assertResponse(
                    client.get("/"), 'value')

        run_coro(run())

    def test_nested(self):
        @api
        class API:
            class endpoint:
                class nested:
                    def get(): ...

        class Impl(TestControllerBase):
            async def nested_get(self, request, context):
                return 'nested'

        async def run():
            async with makeTestClient(API.endpoint, Impl()) as client:
                await self.assertResponse(
                    client.get("/endpoint/nested"), 'nested')

        run_coro(run())

    def test_args(self):
        @api
        class API:
            def GET(arg: str): ...

        class Impl(TestControllerBase):
            async def GET(self, arg: str):
                return arg

        async def run():
            async with makeTestClient(API, Impl()) as client:
                await self.assertResponse(
                    client.get('/?arg="whut"'), 'whut')

        run_coro(run())

    def test_post(self):
        @api
        class API:
            def POST(data: Payload[str]) -> str: ...

        class Impl(TestControllerBase):
            async def POST(self, data: str) -> str:
                return data

        async def run():
            async with makeTestClient(API, Impl()) as client:
                await self.assertResponse(
                    client.post("/", json='value'),
                    'value')

        run_coro(run())

    def test_missing_method(self):
        @api
        class API:
            def GET(arg: str): ...

        class Impl(TestControllerBase):
            pass

        app = web.Application()
        with self.assertRaises(MissingImplementationError) as cm:
            bind(app.router, API, Impl())
        self.assertEqual(cm.exception.methname, "GET")

    def test_signature_checking(self):
        @api
        class API:
            def GET(arg: str): ...

        class Impl(TestControllerBase):
            async def GET(self, arg: int):
                return arg

        app = web.Application()
        with self.assertRaises(SignatureMisatchError) as cm:
            bind(app.router, API, Impl())
        self.assertEqual(cm.exception.methname, "API.GET")

    def test_middleware(self):

        @web.middleware
        async def middleware(request, handler):
            resp = await handler(request)
            exc = resp.get('exception')
            if resp.get('exception') is not None:
                resp.headers['x-error-type'] = type(exc).__name__
            return resp

        @api
        class API:
            def GET() -> str: ...

        class Impl(TestControllerBase):
            async def GET(self) -> str:
                return 1/0

        async def run():
            async with makeTestClient(
                    API, Impl(), middlewares=[middleware]) as client:
                resp = await client.get("/")
                self.assertEqual(
                    resp.headers['x-error-type'], 'ZeroDivisionError')

        run_coro(run())

    def test_controller_for_request(self):

        seen_controller = None

        @web.middleware
        async def middleware(request, handler):
            nonlocal seen_controller
            seen_controller = await controller_for_request(request)
            return await handler(request)

        @api
        class API:
            class meth:
                def GET() -> str: ...

        class Impl(TestControllerBase):
            async def GET(self) -> str:
                return ''

        impl = Impl()

        async def run():
            async with makeTestClient(
                    API.meth, impl, middlewares=[middleware]) as client:
                resp = await client.get("/meth")
                self.assertEqual(await resp.json(), '')

        run_coro(run())

        self.assertIs(impl, seen_controller)
