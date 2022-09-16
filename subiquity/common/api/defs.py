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


class InvalidQueryArgs(Exception):
    def __init__(self, callable, param):
        self.callable = callable
        self.param = param

    def __str__(self):
        return (f"{self.callable.__qualname__} does not serialize query "
                f"arguments but has non-str parameter '{self.param}'")


def api(cls, prefix=(), serialize_query_args=True):
    if hasattr(cls, 'serialize_query_args'):
        serialize_query_args = cls.serialize_query_args
    else:
        cls.serialize_query_args = serialize_query_args
    cls.fullpath = '/' + '/'.join(prefix)
    cls.fullname = prefix
    for k, v in cls.__dict__.items():
        if isinstance(v, type):
            v.__name__ = cls.__name__ + '.' + k
            api(v, prefix + (k,), serialize_query_args)
        if callable(v):
            v.__qualname__ = cls.__name__ + '.' + k
            if not cls.serialize_query_args:
                params = inspect.signature(v).parameters
                for param_name, param in params.items():
                    if param.annotation is not str:
                        raise InvalidQueryArgs(v, param)
    return cls


T = typing.TypeVar("T")


class Payload(typing.Generic[T]):
    pass


def simple_endpoint(typ):
    class endpoint:
        def GET() -> typ: ...
        def POST(data: Payload[typ]): ...
    return endpoint
