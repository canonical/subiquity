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

import inspect
import json

import aiohttp

from subiquitycore import contextlib38

from subiquity.common.serialize import Serializer
from .defs import Payload


def _wrap(make_request, path, meth, serializer):
    sig = inspect.signature(meth)
    meth_params = sig.parameters
    payload_arg = None
    for name, param in meth_params.items():
        if getattr(param.annotation, '__origin__', None) is Payload:
            payload_arg = name
            payload_ann = param.annotation.__args__[0]
    r_ann = sig.return_annotation

    async def impl(*args, **kw):
        args = sig.bind(*args, **kw)
        params = {
            k: json.dumps(serializer.serialize(meth_params[k].annotation, v))
            for (k, v) in args.arguments.items() if k != payload_arg
            }
        if payload_arg in args.arguments:
            v = args.arguments[payload_arg]
            data = serializer.serialize(payload_ann, v)
        else:
            data = None
        async with make_request(
                meth.__name__, path, json=data, params=params) as resp:
            resp.raise_for_status()
            return serializer.deserialize(r_ann, await resp.json())
    return impl


def make_client(endpoint_cls, make_request, serializer=None):
    if serializer is None:
        serializer = Serializer()

    class C:
        pass

    for k, v in endpoint_cls.__dict__.items():
        if isinstance(v, type):
            setattr(C, k, make_client(v, make_request, serializer))
        elif callable(v):
            setattr(C, k, _wrap(
                make_request, endpoint_cls.fullpath, v, serializer))
    return C


def make_client_for_conn(
        endpoint_cls, conn, resp_hook=lambda r: r, serializer=None):
    @contextlib38.asynccontextmanager
    async def make_request(method, path, *, params, json):
        async with aiohttp.ClientSession(
                connector=conn, connector_owner=False) as session:
            async with session.request(
                    method, 'http://a' + path, json=json,
                    params=params, timeout=0) as response:
                yield resp_hook(response)

    return make_client(endpoint_cls, make_request, serializer)
