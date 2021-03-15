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

import datetime
import enum
import json
import inspect
import typing

import attr

# This is basically a half-assed version of # https://pypi.org/project/cattrs/
# but that's not packaged and this is enough for our needs.


class Serializer:

    def __init__(self, *, compact=False):
        self.compact = compact
        self.typing_walkers = {
            typing.Union: self._walk_Union,
            list: self._walk_List,
            typing.List: self._walk_List,
            }
        self.type_serializers = {}
        self.type_deserializers = {}
        for typ in int, str, bool, list, type(None):
            self.type_serializers[typ] = self._scalar
            self.type_deserializers[typ] = self._scalar
        self.type_serializers[dict] = self._serialize_dict
        self.type_deserializers[dict] = self._scalar
        self.type_serializers[datetime.datetime] = self._serialize_datetime
        self.type_deserializers[datetime.datetime] = self._deserialize_datetime

    def _scalar(self, annotation, value, metadata, path):
        assert type(value) is annotation, "at {}, {} is not a {}".format(
            path, value, annotation)
        return value

    def _walk_Union(self, meth, args, value, metadata, path):
        NoneType = type(None)
        assert NoneType in args, "at {}, can only serialize Optional"
        args = [a for a in args if a is not NoneType]
        assert len(args) == 1, "at {}, can only serialize Optional"
        if value is None:
            return value
        return meth(args[0], value, metadata, path)

    def _walk_List(self, meth, args, value, metadata, path):
        return [
            meth(args[0], v, metadata, f'{path}[{i}]')
            for i, v in enumerate(value)
            ]

    def _serialize_dict(self, annotation, value, metadata, path):
        assert type(value) is annotation, "at {}, {} is not a {}".format(
            path, value, annotation)
        for k in value:
            if not isinstance(k, str):
                raise Exception(
                    f"at {path}, dict must have only string keys, found {k!r}")
        return value

    def _serialize_datetime(self, annotation, value, metadata, path):
        assert type(value) is annotation, "at {}, {} is not a {}".format(
            path, value, annotation)
        if metadata is not None and 'time_fmt' in metadata:
            return value.strftime(metadata['time_fmt'])
        else:
            return str(value)

    def _serialize_field(self, field, value, path):
        path = f'{path}.{field.name}'
        return {
            field.name: self.serialize(field.type, value, field.metadata, path)
            }

    def _serialize_attr(self, annotation, value, metadata, path):
        if self.compact:
            r = []
            for field in attr.fields(annotation):
                r.append(self.serialize(
                    field.type, getattr(value, field.name), field.metadata,
                    f'{path}.{field.name}'))
            return r
        else:
            r = {}
            for field in attr.fields(annotation):
                r.update(self._serialize_field(
                    field, getattr(value, field.name), path))
            return r

    def serialize(self, annotation, value, metadata=None, path=''):
        if annotation is None:
            assert value is None
            return None
        if annotation is inspect.Signature.empty:
            return value
        if attr.has(annotation):
            return self._serialize_attr(annotation, value, metadata, path)
        origin = getattr(annotation, '__origin__', None)
        if origin is not None:
            args = annotation.__args__
            return self.typing_walkers[origin](
                self.serialize, args, value, metadata, path)
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            return value.name
        try:
            serializer = self.type_serializers[annotation]
        except KeyError:
            raise Exception(
                "do not know how to handle %s at %s", annotation, path)
        else:
            return serializer(annotation, value, metadata, path)

    def _deserialize_datetime(self, annotation, value, metadata, path):
        assert type(value) is str, f'at {path}'
        if metadata is not None and 'time_fmt' in metadata:
            return datetime.datetime.strptime(value, metadata['time_fmt'])
        else:
            1/0

    def _deserialize_field(self, field, value, path):
        path = f'{path}.{field.name}'
        return {
            field.name: self.deserialize(
                field.type, value, field.metadata, path)
            }

    def _deserialize_attr(self, annotation, value, metadata, path):
        if self.compact:
            args = []
            for field, v in zip(attr.fields(annotation), value):
                args.append(self.deserialize(
                    field.type, v, field.metadata,
                    f'{path}.{field.name}'))
            return annotation(*args)
        else:
            args = {}
            for field in attr.fields(annotation):
                args.update(self._deserialize_field(
                    field, value[field.name], path))
            return annotation(**args)

    def deserialize(self, annotation, value, metadata=None, path=''):
        if annotation is None:
            assert value is None
            return None
        if annotation is inspect.Signature.empty:
            return value
        if attr.has(annotation):
            return self._deserialize_attr(annotation, value, metadata, path)
        origin = getattr(annotation, '__origin__', None)
        if origin is not None:
            args = annotation.__args__
            return self.typing_walkers[origin](
                self.deserialize, args, value, metadata, path)
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            return getattr(annotation, value)
        return self.type_deserializers[annotation](
            annotation, value, metadata, path)

    def to_json(self, annotation, value):
        return json.dumps(self.serialize(annotation, value))

    def from_json(self, annotation, value):
        return self.deserialize(annotation, json.loads(value))


_serializer = Serializer()
to_json = _serializer.to_json
from_json = _serializer.from_json
