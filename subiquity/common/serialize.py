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
import inspect
import typing

import attr

# This is basically a half-assed version of # https://pypi.org/project/cattrs/
# but that's not packaged and this is enough for our needs.


class Serializer:

    def __init__(self):
        self.typing_walkers = {
            typing.Union: self._walk_Union,
            list: self._walk_List,
            typing.List: self._walk_List,
            }
        self.type_serializers = {}
        self.type_deserializers = {}
        for typ in int, str, dict, bool, list, type(None):
            self.type_serializers[typ] = self._scalar
            self.type_deserializers[typ] = self._scalar
        self.type_serializers[datetime.datetime] = self._serialize_datetime
        self.type_deserializers[datetime.datetime] = self._deserialize_datetime

    def _scalar(self, annotation, value, metadata):
        assert type(value) is annotation, "{} is not a {}".format(
            value, annotation)
        return value

    def _walk_Union(self, meth, args, value, metadata):
        NoneType = type(None)
        assert NoneType in args, "can only serialize Optional"
        args = [a for a in args if a is not NoneType]
        assert len(args) == 1, "can only serialize Optional"
        if value is None:
            return value
        return meth(args[0], value, metadata)

    def _walk_List(self, meth, args, value, metadata):
        return [meth(args[0], v, metadata) for v in value]

    def _serialize_datetime(self, annotation, value, metadata):
        assert type(value) is annotation
        if metadata is not None and 'time_fmt' in metadata:
            return value.strftime(metadata['time_fmt'])
        else:
            return str(value)

    def _serialize_field(self, field, value):
        return {field.name: self.serialize(field.type, value, field.metadata)}

    def _serialize_attr(self, annotation, value, metadata):
        r = {}
        for field in attr.fields(annotation):
            r.update(self._serialize_field(field, getattr(value, field.name)))
        return r

    def serialize(self, annotation, value, metadata=None):
        if annotation is None:
            assert value is None
            return None
        if annotation is inspect.Signature.empty:
            return value
        if attr.has(annotation):
            return self._serialize_attr(annotation, value, metadata)
        origin = getattr(annotation, '__origin__', None)
        if origin is not None:
            args = annotation.__args__
            return self.typing_walkers[origin](
                self.serialize, args, value, metadata)
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            return value.name
        return self.type_serializers[annotation](annotation, value, metadata)

    def _deserialize_datetime(self, annotation, value, metadata):
        assert type(value) is str
        if metadata is not None and 'time_fmt' in metadata:
            return datetime.datetime.strptime(value, metadata['time_fmt'])
        else:
            1/0

    def _deserialize_field(self, field, value):
        return {
            field.name: self.deserialize(field.type, value, field.metadata)
            }

    def _deserialize_attr(self, annotation, value, metadata):
        args = {}
        for field in attr.fields(annotation):
            args.update(self._deserialize_field(field, value[field.name]))
        return annotation(**args)

    def deserialize(self, annotation, value, metadata=None):
        if annotation is None:
            assert value is None
            return None
        if annotation is inspect.Signature.empty:
            return value
        if attr.has(annotation):
            return self._deserialize_attr(annotation, value, metadata)
        origin = getattr(annotation, '__origin__', None)
        if origin is not None:
            args = annotation.__args__
            return self.typing_walkers[origin](
                self.deserialize, args, value, metadata)
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            return getattr(annotation, value)
        return self.type_deserializers[annotation](annotation, value, metadata)
