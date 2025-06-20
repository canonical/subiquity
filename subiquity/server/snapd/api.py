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

import asyncio
import contextlib
import json
import logging
import tempfile
from typing import List

import aiohttp

from subiquity.common.api.client import make_client
from subiquity.common.api.defs import Payload, api, path_parameter
from subiquity.common.serialize import Serializer
from subiquity.common.types import Change, TaskStatus
from subiquity.server.snapd.types import (
    ChangeID,
    Response,
    ResponseType,
    Snap,
    SnapActionRequest,
    SystemActionRequest,
    SystemDetails,
    SystemsResponse,
)

log = logging.getLogger("subiquity.server.snapd.api")


@api
class SnapdAPI:
    serialize_query_args = False
    log_responses = False

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
            def GET(name: str = "", select: str = "") -> List[Snap]: ...

        class systems:
            def GET() -> SystemsResponse: ...

            @path_parameter
            class label:
                def GET() -> SystemDetails: ...

                # TODO The return type is correct only for async responses, but
                # not all responses are async. We'd need to extend support for
                # Union types e.g., Union[ChangeID, SystemActionResponse]
                def POST(action: Payload[SystemActionRequest]) -> ChangeID: ...


class _FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    async def json(self):
        return self.data


class _FakeError(_FakeResponse):
    def raise_for_status(self):
        raise aiohttp.ClientError(self.data["result"]["message"])

    async def json(self):
        return self.data["result"]


def make_api_client(async_snapd, log_responses=False, *, api_class=SnapdAPI):
    # subiquity.common.api.client is designed around how to make requests
    # with aiohttp's client code, not the AsyncSnapd API but with a bit of
    # effort it can be contorted into shape. Clearly it would be better to
    # use aiohttp to talk to snapd but that would require porting across
    # the fake implementation used in dry-run mode.

    @contextlib.asynccontextmanager
    async def make_request(method, path, *, params, json, raise_for_status):
        if method == "GET":
            content = await async_snapd.get(
                path[1:], raise_for_status=raise_for_status, **params
            )
        else:
            content = await async_snapd.post(
                path[1:], json, raise_for_status=raise_for_status, **params
            )
        if log_responses:
            log_json_response(content, path.replace("/", "_"))
        response = snapd_serializer.deserialize(Response, content)
        if response.type == ResponseType.SYNC:
            content = content["result"]
        elif response.type == ResponseType.ASYNC:
            content = content["change"]
        elif response.type == ResponseType.ERROR:
            yield _FakeError(content)
            return
        yield _FakeResponse(content)

    client = make_client(api_class, make_request, serializer=snapd_serializer)
    client.log_responses = log_responses
    return client


snapd_serializer = Serializer(ignore_unknown_fields=True, serialize_enums_by="value")


async def post_and_wait(client, meth, *args, ann=None, **kw):
    change_id = await meth(*args, **kw)
    log.debug("post_and_wait %s", change_id)

    while True:
        result = await client.v2.changes[change_id].GET()
        if result.status == TaskStatus.DONE:
            data = result.data
            if client.log_responses:
                log_json_response(data)
            if ann is not None:
                data = snapd_serializer.deserialize(ann, data)
            return data
        elif result.status == TaskStatus.ERROR:
            raise aiohttp.ClientError(result.err)
        await asyncio.sleep(0.1)


def log_json_response(data, label=None):
    """Write the received response to a unique filename.  Useful for developer
    purposes - in some cases, crafting the correct request to snapd can require
    some tricky system setup, so this simplifies capturing the response."""

    prefix = "snapd."
    if label is not None:
        prefix += label + "."
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir="/tmp",
        prefix=prefix,
        suffix=".json",
        delete=False,
        delete_on_close=False,
    ) as fp:
        json.dump(data, fp)
