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
import typing


class InvalidAPIDefinition(Exception):
    pass


class InvalidQueryArgs(InvalidAPIDefinition):
    def __init__(self, callable, param):
        self.callable = callable
        self.param = param

    def __str__(self):
        return (
            f"{self.callable.__qualname__} does not serialize query "
            f"arguments but has non-str parameter '{self.param}'"
        )


class MultiplePathParameters(InvalidAPIDefinition):
    def __init__(self, cls, param1, param2):
        self.cls = cls
        self.param1 = param1
        self.param2 = param2

    def __str__(self):
        return (
            f"{self.cls.__name__} has multiple path parameters "
            f"{self.param1!r} and {self.param2!r}"
        )


def api(
    cls, prefix_names=(), prefix_path=(), path_params=(), serialize_query_args=True
):
    if hasattr(cls, "serialize_query_args"):
        serialize_query_args = cls.serialize_query_args
    else:
        cls.serialize_query_args = serialize_query_args
    cls.fullpath = "/" + "/".join(prefix_path)
    cls.fullname = prefix_names
    seen_path_param = None
    for k, v in cls.__dict__.items():
        if isinstance(v, type):
            v.__shortname__ = k
            v.__name__ = cls.__name__ + "." + k
            path_part = k
            path_param = ()
            if getattr(v, "__parameter__", False):
                if seen_path_param:
                    raise MultiplePathParameters(cls, seen_path_param, k)
                seen_path_param = k
                path_part = "{" + path_part + "}"
                path_param = (k,)
            api(
                v,
                prefix_names + (k,),
                prefix_path + (path_part,),
                path_params + path_param,
                serialize_query_args,
            )
        if callable(v):
            v.__qualname__ = cls.__name__ + "." + k
            if not cls.serialize_query_args:
                params = inspect.signature(v).parameters
                for param_name, param in params.items():
                    if (
                        param.annotation is not str
                        and getattr(param.annotation, "__origin__", None) is not Payload
                    ):
                        raise InvalidQueryArgs(v, param)
            v.__path_params__ = path_params
    return cls


T = typing.TypeVar("T")


class Payload(typing.Generic[T]):
    pass


def path_parameter(cls):
    cls.__parameter__ = True
    return cls


def simple_endpoint(typ):
    class endpoint:
        def GET() -> typ:
            ...

        def POST(data: Payload[typ]):
            ...

    return endpoint


def allowed_before_start(fun):
    """An endpoint may mark themselves as allowed_before_start if they should
    be made usable prior to the controllers starting.  Most endpoints don't
    want this."""
    fun.allowed_before_start = True
    return fun
