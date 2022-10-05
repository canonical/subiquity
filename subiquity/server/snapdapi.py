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

import aiohttp
import asyncio
import contextlib
import enum
import logging
from typing import List

from subiquity.common.api.client import make_client
from subiquity.common.api.defs import api, path_parameter, Payload
from subiquity.common.serialize import named_field, Serializer
from subiquity.common.types import Change, TaskStatus

import attr


log = logging.getLogger('subiquity.server.snapdapi')

RFC3339 = '%Y-%m-%dT%H:%M:%S.%fZ'


def date_field(name=None, default=attr.NOTHING):
    metadata = {'time_fmt': RFC3339}
    if name is not None:
        metadata.update(named_field(name).metadata)
    return attr.ib(metadata=metadata, default=default)


ChangeID = str


class SnapStatus(enum.Enum):
    ACTIVE = 'active'
    AVAILABLE = 'available'


@attr.s(auto_attribs=True)
class Publisher:
    id: str
    username: str
    display_name: str = named_field('display-name')


@attr.s(auto_attribs=True)
class Snap:
    id: str
    name: str
    status: SnapStatus
    publisher: Publisher
    version: str
    revision: str
    channel: str


class SnapAction(enum.Enum):
    REFRESH = 'refresh'
    SWITCH = 'switch'


@attr.s(auto_attribs=True)
class SnapActionRequest:
    action: SnapAction
    channel: str = ''
    ignore_running: bool = named_field('ignore-running', False)


class ResponseType:
    SYNC = 'sync'
    ASYNC = 'async'
    ERROR = 'error'


@attr.s(auto_attribs=True)
class Response:
    type: str
    status_code: int = named_field("status-code")
    status: str


@api
class SnapdAPI:
    serialize_query_args = False

    class v2:
        class changes:
            @path_parameter
            class change_id:
                def GET() -> Change: ...

        class snaps:
            @path_parameter
            class snap_name:
                def GET() -> Snap: ...
                def POST(action: Payload[SnapActionRequest]) -> ChangeID: ...

        class find:
            def GET(name: str = '', select: str = '') -> List[Snap]: ...


class _FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    async def json(self):
        return self.data


class _FakeError:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        raise aiohttp.ClientError(self.data['result']['message'])


def make_api_client(async_snapd):
    # subiquity.common.api.client is designed around how to make requests
    # with aiohttp's client code, not the AsyncSnapd API but with a bit of
    # effort it can be contorted into shape. Clearly it would be better to
    # use aiohttp to talk to snapd but that would require porting across
    # the fake implementation used in dry-run mode.

    @contextlib.asynccontextmanager
    async def make_request(method, path, *, params, json):
        if method == "GET":
            content = await async_snapd.get(path[1:], **params)
        else:
            content = await async_snapd.post(path[1:], json, **params)
        response = serializer.deserialize(Response, content)
        if response.type == ResponseType.SYNC:
            content = content['result']
        elif response.type == ResponseType.ASYNC:
            content = content['change']
        elif response.type == ResponseType.ERROR:
            yield _FakeError()
        yield _FakeResponse(content)

    serializer = Serializer(
        ignore_unknown_fields=True, serialize_enums_by='value')

    return make_client(SnapdAPI, make_request, serializer=serializer)


async def post_and_wait(client, meth, *args, **kw):
    change_id = await meth(*args, **kw)
    log.debug('post_and_wait %s', change_id)

    while True:
        result = await client.v2.changes[change_id].GET()
        if result.status == TaskStatus.DONE:
            return result.data
        await asyncio.sleep(0.1)
