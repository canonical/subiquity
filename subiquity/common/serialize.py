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
import json
import typing

import attr


def named_field(name, default=attr.NOTHING):
    return attr.ib(metadata={"name": name}, default=default)


def _field_name(field):
    return field.metadata.get("name", field.name)


class SerializationError(Exception):
    def __init__(self, obj, path, message):
        self.obj = obj
        self.path = path
        self.message = message

    def __str__(self):
        p = self.path
        if not p:
            p = "top-level"
        return f"processing {self.obj}: at {p}, {self.message}"


E = typing.TypeVar("E")


class NonExhaustive(typing.Generic[E]):
    pass


@attr.s(auto_attribs=True)
class SerializationContext:
    obj: typing.Any
    cur: typing.Any
    path: str
    metadata: typing.Optional[typing.Dict]
    serializing: bool

    @classmethod
    def new(cls, obj, *, serializing):
        return SerializationContext(obj, obj, "", {}, serializing)

    def child(self, path, cur, metadata=None):
        if metadata is None:
            metadata = self.metadata
        return attr.evolve(self, path=self.path + path, cur=cur, metadata=metadata)

    def error(self, message):
        raise SerializationError(self.obj, self.path, message)

    def assert_type(self, typ):
        if type(self.cur) is not typ:
            self.error("{!r} is not a {}".format(self.cur, typ))


# This is basically a half-assed version of # https://pypi.org/project/cattrs/
# but that's not packaged and this is enough for our needs.

_enum_has_str_values = {}


class Serializer:
    def __init__(
        self, *, compact=False, ignore_unknown_fields=False, serialize_enums_by="name"
    ):
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
            NonExhaustive: self._walk_NonExhaustive,
        }
        self.type_serializers = {}
        self.type_deserializers = {}
        for typ in int, float, str, bool, list, type(None):
            self.type_serializers[typ] = self._scalar
            self.type_deserializers[typ] = self._scalar
        self.type_serializers[dict] = self._serialize_dict
        self.type_deserializers[dict] = self._scalar
        self.type_serializers[datetime.datetime] = self._serialize_datetime
        self.type_deserializers[datetime.datetime] = self._deserialize_datetime

    def _ann_ok_as_dict_key(self, annotation):
        if annotation is str:
            return True
        origin = getattr(annotation, "__origin__", None)
        if origin is NonExhaustive:
            annotation = annotation.__args__[0]
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            if self.serialize_enums_by == "name":
                return True
            else:
                if annotation in _enum_has_str_values:
                    return _enum_has_str_values[annotation]
                ok = set(type(v.value) for v in annotation) == {str}
                _enum_has_str_values[annotation] = ok
                return ok
        else:
            return False

    def _scalar(self, annotation, context):
        context.assert_type(annotation)
        return context.cur

    def _walk_Union(self, meth, args, context):
        NoneType = type(None)
        if NoneType in args:
            args = [a for a in args if a is not NoneType]
            if context.cur is None:
                return context.cur
            if len(args) == 1:
                # I.e. Optional[thing]
                return meth(args[0], context)
        if all(attr.has(a) for a in args):
            if context.serializing:
                for a in args:
                    if isinstance(context.cur, a):
                        r = meth(a, context)
                        if self.compact:
                            r.insert(0, a.__name__)
                        else:
                            r["$type"] = a.__name__
                        return r
                context.error(f"type of {context.cur} not found in {args}")
            else:
                if self.compact:
                    n = context.cur.pop(0)
                else:
                    n = context.cur.pop("$type")
                for a in args:
                    if a.__name__ == n:
                        return meth(a, context)
                context.error(f"type {n} not found in {args}")
        elif all(t in (int, str, float, bool) for t in args):
            data = context.cur
            for type_ in args:
                if isinstance(data, type_):
                    return meth(type_, context)

        raise context.error(f"cannot serialize Union[{args}]")

    def _walk_List(self, meth, args, context):
        return [
            meth(args[0], context.child(f"[{i}]", v)) for i, v in enumerate(context.cur)
        ]

    def _walk_Dict(self, meth, args, context):
        k_ann, v_ann = args
        if self._ann_ok_as_dict_key(k_ann):
            input_items = context.cur.items()
        elif context.serializing:
            input_items = context.cur.items()
        else:
            input_items = context.cur
        output_items = [
            [
                meth(k_ann, context.child(f"/{k}", k)),
                meth(v_ann, context.child(f"[{k}]", v)),
            ]
            for k, v in input_items
        ]
        if self._ann_ok_as_dict_key(k_ann):
            return dict(output_items)
        elif context.serializing:
            return output_items
        else:
            return dict(output_items)

    def _walk_NonExhaustive(self, meth, args, context):
        [enum_cls] = args
        if context.serializing:
            if isinstance(context.cur, enum_cls):
                return meth(enum_cls, context)
            else:
                return context.cur
        else:
            if context.cur in (getattr(m, self.serialize_enums_by) for m in enum_cls):
                return meth(enum_cls, context)
            else:
                return context.cur

    def _serialize_dict(self, annotation, context):
        context.assert_type(annotation)
        for k in context.cur:
            context.child(f"/{k}", k).assert_type(str)
        return context.cur

    def _serialize_datetime(self, annotation, context):
        context.assert_type(annotation)
        fmt = context.metadata.get("time_fmt")
        if fmt is not None:
            return context.cur.strftime(fmt)
        else:
            return str(context.cur)

    def _serialize_attr(self, annotation, context):
        serialized = []
        for field in attr.fields(annotation):
            serialized.append(
                (
                    _field_name(field),
                    self._serialize(
                        field.type,
                        context.child(
                            f".{field.name}",
                            getattr(context.cur, field.name),
                            field.metadata,
                        ),
                    ),
                )
            )
        if self.compact:
            return [s[1] for s in serialized]
        else:
            return dict(serialized)

    def _serialize_enum(self, annotation, context):
        context.assert_type(annotation)
        return getattr(context.cur, self.serialize_enums_by)

    def _serialize(self, annotation, context):
        if annotation is None:
            context.assert_type(type(None))
            return None
        if annotation is inspect.Signature.empty or annotation is typing.Any:
            return context.cur
        if attr.has(annotation):
            return self._serialize_attr(annotation, context)
        origin = getattr(annotation, "__origin__", None)
        if origin is not None:
            args = annotation.__args__
            return self.typing_walkers[origin](self._serialize, args, context)
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            return self._serialize_enum(annotation, context)
        try:
            serializer = self.type_serializers[annotation]
        except KeyError:
            context.error(f"do not know how to handle {annotation}")
        else:
            return serializer(annotation, context)

    def serialize(self, annotation, value):
        context = SerializationContext.new(value, serializing=True)
        return self._serialize(annotation, context)

    def _deserialize_datetime(self, annotation, context):
        fmt = context.metadata.get("time_fmt")
        if fmt is None:
            context.error("cannot serialize datetime without format")
        return datetime.datetime.strptime(context.cur, fmt)

    def _deserialize_attr(self, annotation, context):
        if self.compact:
            context.assert_type(list)
            args = []
            for field, value in zip(attr.fields(annotation), context.cur):
                args.append(
                    self._deserialize(
                        field.type,
                        context.child(f"[{field.name!r}]", value, field.metadata),
                    )
                )
            return annotation(*args)
        else:
            context.assert_type(dict)
            args = {}
            fields = {_field_name(field): field for field in attr.fields(annotation)}
            for key, value in context.cur.items():
                if key not in fields and (key == "$type" or self.ignore_unknown_fields):
                    # Union types can contain a '$type' field that is not
                    # actually one of the keys.  This happens if a object is
                    # serialized as part of a Union, sent to an API caller,
                    # then received back on a different endpoint that isn't a
                    # Union.
                    continue
                field = fields[key]
                args[field.name] = self._deserialize(
                    field.type, context.child(f"[{key!r}]", value, field.metadata)
                )
            return annotation(**args)

    def _deserialize_enum(self, annotation, context):
        if self.serialize_enums_by == "name":
            return getattr(annotation, context.cur)
        else:
            return annotation(context.cur)

    def _deserialize(self, annotation, context):
        if annotation is None:
            context.assert_type(type(None))
            return None
        if annotation is inspect.Signature.empty or annotation is typing.Any:
            return context.cur
        if attr.has(annotation):
            return self._deserialize_attr(annotation, context)
        origin = getattr(annotation, "__origin__", None)
        if origin is not None:
            return self.typing_walkers[origin](
                self._deserialize, annotation.__args__, context
            )
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            return self._deserialize_enum(annotation, context)
        return self.type_deserializers[annotation](annotation, context)

    def deserialize(self, annotation, value):
        context = SerializationContext.new(value, serializing=False)
        return self._deserialize(annotation, context)

    def to_json(self, annotation, value):
        return json.dumps(self.serialize(annotation, value))

    def from_json(self, annotation, value):
        return self.deserialize(annotation, json.loads(value))


_serializer = Serializer()
to_json = _serializer.to_json
from_json = _serializer.from_json
