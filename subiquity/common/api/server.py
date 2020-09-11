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

from aiohttp import web

from subiquity.common.serialize import Serializer

from .defs import Payload


class BindError(Exception):
    pass


class MissingImplementationError(BindError):
    def __init__(self, controller, methname):
        self.controller = controller
        self.methname = methname

    def __str__(self):
        return f"{self.controller} must have method called {self.methname}"


class SignatureMisatchError(BindError):
    def __init__(self, methname, expected, actual):
        self.methname = methname
        self.expected = expected
        self.actual = actual

    def __str__(self):
        return (f"implementation of {self.methname} has wrong signature, "
                f"should be {self.expected} but is {self.actual}")


def trim(text):
    if text is None:
        return ''
    elif len(text) > 80:
        return text[:77] + '...'
    else:
        return text


def _make_handler(controller, definition, implementation, serializer):
    def_sig = inspect.signature(definition)
    def_ret_ann = def_sig.return_annotation
    def_params = def_sig.parameters

    impl_sig = inspect.signature(implementation)
    impl_params = impl_sig.parameters

    data_annotation = None
    data_arg = None
    query_args_anns = []

    check_def_params = []

    for param_name, param in def_params.items():
        if param_name in ('request', 'context'):
            raise Exception(
                "api method {} cannot have parameter called request or "
                "context".format(definition))
        if getattr(param.annotation, '__origin__', None) is Payload:
            data_arg = param_name
            data_annotation = param.annotation.__args__[0]
            check_def_params.append(param.replace(annotation=data_annotation))
        else:
            query_args_anns.append(
                (param_name, param.annotation, param.default))
            check_def_params.append(param)

    check_impl_params = [
        p for p in impl_params.values()
        if p.name not in ('context', 'request')
        ]
    check_impl_sig = impl_sig.replace(parameters=check_impl_params)

    check_def_sig = def_sig.replace(parameters=check_def_params)

    if check_impl_sig != check_def_sig:
        raise SignatureMisatchError(
            definition.__qualname__, check_def_sig, check_impl_sig)

    async def handler(request):
        context = controller.context.child(
            implementation.__name__, trim(await request.text()))
        with context:
            context.set('request', request)
            args = {}
            if data_annotation is not None:
                payload = json.loads(await request.text())
                args[data_arg] = serializer.deserialize(
                    data_annotation, payload)
            for arg, ann, default in query_args_anns:
                if arg in request.query:
                    v = serializer.deserialize(
                        ann, json.loads(request.query[arg]))
                elif default != inspect._empty:
                    v = default
                else:
                    1/0
                args[arg] = v
            if 'context' in impl_params:
                args['context'] = context
            if 'request' in impl_params:
                args['request'] = request
            try:
                result = await implementation(**args)
                resp = web.json_response(
                    serializer.serialize(def_ret_ann, result),
                    headers={'x-status': 'ok'})
            except Exception as exc:
                resp = web.Response(
                    status=500,
                    headers={'x-status': 'error'})
                resp['exception'] = exc
            context.description = '{} {}'.format(resp.status, trim(resp.text))
            return resp
    handler.controller = controller

    return handler


async def controller_for_request(request):
    match_info = await request.app.router.resolve(request)
    return getattr(match_info.handler, 'controller', None)


def bind(router, endpoint, controller, serializer=None, _depth=None):
    if serializer is None:
        serializer = Serializer()
    if _depth is None:
        _depth = len(endpoint.fullname)

    for v in endpoint.__dict__.values():
        if isinstance(v, type):
            bind(router, v, controller, serializer, _depth)
        elif callable(v):
            method = v.__name__
            impl_name = "_".join(endpoint.fullname[_depth:] + (method,))
            if not hasattr(controller, impl_name):
                raise MissingImplementationError(controller, impl_name)
            impl = getattr(controller, impl_name)
            router.add_route(
                method=method,
                path=endpoint.fullpath,
                handler=_make_handler(controller, v, impl, serializer))


async def make_server_at_path(socket_path, endpoint, controller):
    app = web.Application()
    bind(app.router, endpoint, controller)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.UnixSite(runner, socket_path)
    await site.start()
    return site
