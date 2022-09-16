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


def named_field(name, default=attr.NOTHING):
    return attr.ib(metadata={'name': name}, default=default)


def _field_name(field):
    return field.metadata.get('name', field.name)


# This is basically a half-assed version of # https://pypi.org/project/cattrs/
# but that's not packaged and this is enough for our needs.


class Serializer:

    def __init__(self, *, compact=False, ignore_unknown_fields=False,
                 serialize_enums_by="name"):
        self.compact = compact
        self.ignore_unknown_fields = ignore_unknown_fields
        assert serialize_enums_by in ("value", "name")
        self.serialize_enums_by = serialize_enums_by
        self.typing_walkers = {
            typing.Union: self._walk_Union,
            list: self._walk_List,
            typing.List: self._walk_List,
            dict: self._walk_Dict,
            typing.Dict: self._walk_Dict,
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
        assert type(value) is annotation, "at {}, {!r} is not a {}".format(
            path, value, annotation)
        return value

    def _walk_Union(self, meth, args, value, metadata, path, serializing):
        NoneType = type(None)
        if NoneType in args:
            args = [a for a in args if a is not NoneType]
            if len(args) == 1:
                # I.e. Optional[thing]
                if value is None:
                    return value
                return meth(args[0], value, metadata, path)
        if all(attr.has(a) for a in args):
            if serializing:
                for a in args:
                    if isinstance(value, a):
                        r = meth(a, value, metadata, path)
                        if self.compact:
                            r.insert(0, a.__name__)
                        else:
                            r['$type'] = a.__name__
                        return r
                raise Exception(
                    f"at {path}, type of {value} not found in {args}")
            else:
                if self.compact:
                    n = value.pop(0)
                else:
                    n = value.pop('$type')
                for a in args:
                    if a.__name__ == n:
                        return meth(a, value, metadata, path)
                raise Exception(f"at {path}, type {n} not found in {args}")
        raise Exception(f"at {path}, cannot serialize Union[{args}]")

    def _walk_List(self, meth, args, value, metadata, path, serializing):
        return [
            meth(args[0], v, metadata, f'{path}[{i}]')
            for i, v in enumerate(value)
            ]

    def _walk_Dict(self, meth, args, value, m, p, serializing):
        k_ann, v_ann = args
        if k_ann is str:
            return {
                meth(k_ann, k, m, f'{p}/{k}'): meth(v_ann, v, m, f'{p}[{k}]')
                for k, v in value.items()
                }
        elif serializing:
            return [
                [meth(k_ann, k, m, f'{p}/{k}'), meth(v_ann, v, m, f'{p}[{k}]')]
                for k, v in value.items()
                ]
        else:
            return dict([
                (meth(k_ann, k, m, f'{p}/{k}'), meth(v_ann, v, m, f'{p}[{k}]'))
                for k, v in value
                ])

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
            _field_name(field): self.serialize(
                field.type, value, field.metadata, path)
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

    def _serialize_enum(self, annotation, value):
        return getattr(value, self.serialize_enums_by)

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
                self.serialize, args, value, metadata, path, True)
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            return self._serialize_enum(annotation, value)
        try:
            serializer = self.type_serializers[annotation]
        except KeyError:
            raise Exception(
                f"do not know how to handle {annotation} at {path}")
        else:
            return serializer(annotation, value, metadata, path)

    def _deserialize_datetime(self, annotation, value, metadata, path):
        assert type(value) is str, f'at {path}'
        if metadata is not None and 'time_fmt' in metadata:
            return datetime.datetime.strptime(value, metadata['time_fmt'])
        else:
            1/0

    def _deserialize_field(self, field, value, path):
        name = _field_name(field)
        path = f'{path}.{name}'
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
            fields = {
                _field_name(field): field for field in attr.fields(annotation)
                }
            for key in value.keys():
                if key not in fields and (
                        key == '$type' or self.ignore_unknown_fields):
                    # Union types can contain a '$type' field that is not
                    # actually one of the keys.  This happens if a object is
                    # serialized as part of a Union, sent to an API caller,
                    # then received back on a different endpoint that isn't a
                    # Union.
                    continue
                args.update(self._deserialize_field(
                    fields[key], value[key], path))
            return annotation(**args)

    def _deserialize_enum(self, annotation, value):
        if self.serialize_enums_by == "name":
            return getattr(annotation, value)
        else:
            return annotation(value)

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
                self.deserialize, args, value, metadata, path, False)
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            return self._deserialize_enum(annotation, value)
        return self.type_deserializers[annotation](
            annotation, value, metadata, path)

    def to_json(self, annotation, value):
        return json.dumps(self.serialize(annotation, value))

    def from_json(self, annotation, value):
        return self.deserialize(annotation, json.loads(value))


_serializer = Serializer()
to_json = _serializer.to_json
from_json = _serializer.from_json
