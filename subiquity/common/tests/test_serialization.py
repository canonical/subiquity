# Copyright 2021 Canonical, Ltd.
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
import random
import string
import typing
import unittest

import attr

from subiquity.common.serialize import (
    NonExhaustive,
    SerializationError,
    Serializer,
    named_field,
)


@attr.s(auto_attribs=True)
class Data:
    field1: str
    field2: int

    @staticmethod
    def make_random():
        return Data(random.choice(string.ascii_letters), random.randint(0, 1000))


@attr.s(auto_attribs=True)
class Container:
    data: Data
    data_list: typing.List[Data]

    @staticmethod
    def make_random():
        return Container(
            data=Data.make_random(),
            data_list=[Data.make_random() for i in range(random.randint(10, 20))],
        )


@attr.s(auto_attribs=True)
class OptionalAndDefault:
    int: int
    optional_int: typing.Optional[int]
    int_default: int = 3
    optional_int_default: typing.Optional[int] = 4


class MyEnum(enum.Enum):
    name = "value"


class MyIntEnum(enum.Enum):
    name = 1


class CommonSerializerTests:
    simple_examples = [
        (int, 1),
        (str, "v"),
        (list, [1]),
        (dict, {"2": 3}),
        (type(None), None),
    ]

    def assertSerializesTo(self, annotation, value, expected):
        self.assertEqual(self.serializer.serialize(annotation, value), expected)

    def assertDeserializesTo(self, annotation, value, expected):
        self.assertEqual(self.serializer.deserialize(annotation, value), expected)

    def assertRoundtrips(self, annotation, value):
        serialized = self.serializer.to_json(annotation, value)
        self.assertEqual(self.serializer.from_json(annotation, serialized), value)

    def assertSerialization(self, annotation, value, expected):
        self.assertSerializesTo(annotation, value, expected)
        self.assertDeserializesTo(annotation, expected, value)

    def assertSerializesToErrors(self, annotation, value):
        with self.assertRaises(SerializationError):
            self.serializer.serialize(annotation, value)

    def assertDeserializesToErrors(self, annotation, value):
        with self.assertRaises(SerializationError):
            self.serializer.deserialize(annotation, value)

    def assertSerializationErrors(self, annotation, value):
        self.assertSerializesToErrors(annotation, value)
        self.assertDeserializesToErrors(annotation, value)

    def test_roundtrip_scalars(self):
        for typ, val in self.simple_examples:
            self.assertRoundtrips(typ, val)

    def test_roundtrip_optional(self):
        self.assertRoundtrips(typing.Optional[int], None)
        self.assertRoundtrips(typing.Optional[int], 1)

    def test_roundtrip_list(self):
        self.assertRoundtrips(typing.List[str], ["a"])
        self.assertRoundtrips(typing.List[int], [23])

    def test_roundtrip_attr(self):
        self.assertRoundtrips(Data, Data.make_random())
        self.assertRoundtrips(Container, Container.make_random())

    def test_scalars(self):
        for typ, val in self.simple_examples:
            self.assertSerialization(typ, val, val)

    def test_non_string_key_dict(self):
        self.assertRaises(Exception, self.serializer.serialize, dict, {1: 2})

    def test_roundtrip_dict(self):
        ann = typing.Dict[int, str]
        self.assertRoundtrips(ann, {1: "2"})

    def test_roundtrip_dict_strkey(self):
        ann = typing.Dict[str, int]
        self.assertRoundtrips(ann, {"a": 2})

    def test_serialize_dict(self):
        self.assertSerialization(typing.Dict[int, str], {1: "a"}, [[1, "a"]])

    def test_serialize_dict_strkeys(self):
        self.assertSerialization(typing.Dict[str, str], {"a": "b"}, {"a": "b"})

    def test_rountrip_union(self):
        ann = typing.Union[Data, Container]
        self.assertRoundtrips(ann, Data.make_random())
        self.assertRoundtrips(ann, Container.make_random())

    def test_enums(self):
        self.assertSerialization(MyEnum, MyEnum.name, "name")

    def test_non_exhaustive_enums(self):
        self.serializer = type(self.serializer)(compact=self.serializer.compact)
        self.assertSerialization(NonExhaustive[MyEnum], MyEnum.name, "name")
        self.assertSerialization(NonExhaustive[MyEnum], "name2", "name2")

    def test_enums_by_value(self):
        self.serializer = type(self.serializer)(
            compact=self.serializer.compact, serialize_enums_by="value"
        )
        self.assertSerialization(MyEnum, MyEnum.name, "value")

    def test_non_exhaustive_enums_by_value(self):
        self.serializer = type(self.serializer)(
            compact=self.serializer.compact, serialize_enums_by="value"
        )
        self.assertSerialization(NonExhaustive[MyEnum], MyEnum.name, "value")
        self.assertSerialization(NonExhaustive[MyEnum], "value2", "value2")

    def test_serialize_any(self):
        o = object()
        self.assertSerialization(typing.Any, o, o)
        self.assertSerialization(inspect.Signature.empty, o, o)


class TestSerializer(CommonSerializerTests, unittest.TestCase):
    serializer = Serializer()

    def test_datetime(self):
        @attr.s
        class C:
            d: datetime.datetime = attr.ib(metadata={"time_fmt": "%Y-%m-%d"})

        c = C(datetime.datetime(2022, 1, 1))
        self.assertSerialization(C, c, {"d": "2022-01-01"})

    def test_float(self):
        @attr.s
        class C:
            f: float = attr.ib()

        c = C(0.1)
        self.assertSerialization(C, c, {"f": 0.1})

    def test_serialize_attr(self):
        data = Data.make_random()
        expected = {"field1": data.field1, "field2": data.field2}
        self.assertSerialization(Data, data, expected)

    def test_serialize_container(self):
        data1 = Data.make_random()
        data2 = Data.make_random()
        container = Container(data1, [data2])
        expected = {
            "data": {"field1": data1.field1, "field2": data1.field2},
            "data_list": [
                {"field1": data2.field1, "field2": data2.field2},
            ],
        }
        self.assertSerialization(Container, container, expected)

    def test_serialize_union(self):
        data = Data.make_random()
        expected = {
            "$type": "Data",
            "field1": data.field1,
            "field2": data.field2,
        }
        self.assertSerialization(typing.Union[Data, Container], data, expected)

    def test_serialization_union_scalars(self):
        self.assertSerialization(typing.Union[int, str], 30, 30)
        self.assertSerialization(typing.Union[int, str], "hello", "hello")

        self.assertSerialization(typing.Union[int, float], 30.0, 30.0)
        self.assertSerialization(typing.Union[float, int], 30.0, 30.0)
        self.assertSerialization(typing.Union[int, float], 30, 30)
        self.assertSerialization(typing.Union[float, int], 30, 30)

        self.assertSerialization(typing.Union[bool, str], True, True)
        self.assertSerialization(typing.Union[bool, str], False, False)
        self.assertSerialization(typing.Union[bool, str], "hello", "hello")

        self.assertSerialization(typing.Union[int, float, str], 10, 10)
        self.assertSerialization(typing.Union[int, float, str], "string", "string")
        self.assertSerialization(typing.Union[int, float, str], 5.0, 5.0)

        self.assertSerialization(typing.Union[int, float, str, None], 10, 10)
        self.assertSerialization(typing.Union[int, float, str, None], None, None)

        # This is what Optional[int] does.
        self.assertSerialization(typing.Union[int, type(None)], 10, 10)
        self.assertSerialization(typing.Union[int, type(None)], None, None)

    def test_serialization_union_scalars__errors(self):
        self.assertSerializationErrors(typing.Union[int, str], 5.0)
        self.assertSerializationErrors(typing.Union[int, float], "hello")
        self.assertSerializationErrors(typing.Union[int, float], "5.0")
        self.assertSerializationErrors(typing.Union[str, int], True)

    def test_serialization_union_none_attrs(self):
        @attr.s(auto_attribs=True)
        class A:
            x: int

        @attr.s(auto_attribs=True)
        class B:
            y: int

        self.assertSerialization(typing.Union[type(None), A, B], None, None)
        self.assertSerialization(
            typing.Union[type(None), A, B], A(10), {"$type": "A", "x": 10}
        )
        self.assertSerialization(
            typing.Union[type(None), A, B], B(10), {"$type": "B", "y": 10}
        )

        self.assertSerialization(typing.Union[type(None), A, B], None, None)
        self.assertSerialization(
            typing.Union[type(None), A, B], A(10), {"$type": "A", "x": 10}
        )
        self.assertSerialization(
            typing.Union[type(None), A, B], B(10), {"$type": "B", "y": 10}
        )

    def test_arbitrary_types_may_have_type_field(self):
        # The serializer will add a $type field to data elements in a Union.
        # If we then take that serialized value and fling it back to another
        # API entrypoint, one that isn't taking a Union, it must be cool with
        # the excess $type field.
        data = {
            "$type": "Data",
            "field1": "1",
            "field2": 2,
        }
        expected = Data(field1="1", field2=2)
        self.assertDeserializesTo(Data, data, expected)

    def test_reject_unknown_fields_by_default(self):
        serializer = Serializer()
        data = Data.make_random()
        serialized = serializer.serialize(Data, data)
        serialized["foobar"] = "baz"
        with self.assertRaises(KeyError):
            serializer.deserialize(Data, serialized)

    def test_ignore_unknown_fields(self):
        serializer = Serializer(ignore_unknown_fields=True)
        data = Data.make_random()
        serialized = serializer.serialize(Data, data)
        serialized["foobar"] = "baz"
        self.assertEqual(serializer.deserialize(Data, serialized), data)

    def test_override_field_name(self):
        @attr.s(auto_attribs=True)
        class Object:
            x: int
            y: int = named_field("field-y")
            z: int = named_field("field-z", 0)

        self.assertSerialization(
            Object, Object(1, 2), {"x": 1, "field-y": 2, "field-z": 0}
        )

    def test_embedding(self):
        @attr.s(auto_attribs=True)
        class Base1:
            x: str

        @attr.s(auto_attribs=True)
        class Base2:
            b: Base1

        @attr.s(auto_attribs=True)
        class Derived1(Base1):
            y: int

        @attr.s(auto_attribs=True)
        @attr.s(auto_attribs=True)
        class Derived2(Base2):
            b: Derived1
            c: int

        self.assertSerialization(
            Derived2,
            Derived2(b=Derived1(x="a", y=1), c=2),
            {"b": {"x": "a", "y": 1}, "c": 2},
        )

    def test_error_paths(self):
        with self.assertRaises(SerializationError) as catcher:
            self.serializer.serialize(str, 1)
        self.assertEqual(catcher.exception.path, "")

        @attr.s(auto_attribs=True)
        class Type:
            field1: str = named_field("field-1")
            field2: int

        with self.assertRaises(SerializationError) as catcher:
            self.serializer.serialize(Type, Data(2, 3))
        self.assertEqual(catcher.exception.path, ".field1")
        with self.assertRaises(SerializationError) as catcher:
            self.serializer.deserialize(Type, {"field-1": 1, "field2": 2})
        self.assertEqual(catcher.exception.path, "['field-1']")

    def test_serialize_dict_enumkeys_name(self):
        self.assertSerialization(
            typing.Dict[MyEnum, str], {MyEnum.name: "b"}, {"name": "b"}
        )

    def test_serialize_dict_enumkeys_str_value(self):
        self.serializer = type(self.serializer)(
            compact=self.serializer.compact, serialize_enums_by="value"
        )
        self.assertSerialization(
            typing.Dict[MyEnum, str], {MyEnum.name: "b"}, {"value": "b"}
        )

    def test_serialize_dict_enumkeys_notstr_value(self):
        self.serializer = type(self.serializer)(
            compact=self.serializer.compact, serialize_enums_by="value"
        )
        self.assertSerialization(
            typing.Dict[MyIntEnum, str],
            {MyIntEnum.name: "b"},
            [[1, "b"]],
        )


class TestCompactSerializer(CommonSerializerTests, unittest.TestCase):
    serializer = Serializer(compact=True)

    def test_serialize_attr(self):
        data = Data.make_random()
        expected = [data.field1, data.field2]
        self.assertSerialization(Data, data, expected)

    def test_serialize_container(self):
        data1 = Data.make_random()
        data2 = Data.make_random()
        container = Container(data1, [data2])
        expected = [
            [data1.field1, data1.field2],
            [[data2.field1, data2.field2]],
        ]
        self.assertSerialization(Container, container, expected)

    def test_serialize_union(self):
        data = Data.make_random()
        expected = ["Data", data.field1, data.field2]
        self.assertSerialization(typing.Union[Data, Container], data, expected)


class TestOptionalAndDefault(CommonSerializerTests, unittest.TestCase):
    serializer = Serializer()

    def test_happy(self):
        data = {
            "int": 11,
            "optional_int": 12,
            "int_default": 3,
            "optional_int_default": 4,
        }
        expected = OptionalAndDefault(11, 12)
        self.assertDeserializesTo(OptionalAndDefault, data, expected)

    def test_skip_int(self):
        data = {"optional_int": 12, "int_default": 13, "optional_int_default": 14}

        with self.assertRaises(TypeError):
            self.serializer.deserialize(OptionalAndDefault, data)

    def test_skip_optional_int(self):
        data = {"int": 11, "int_default": 13, "optional_int_default": 14}

        with self.assertRaises(TypeError):
            self.serializer.deserialize(OptionalAndDefault, data)

    def test_optional_int_none(self):
        data = {
            "int": 11,
            "optional_int": None,
            "int_default": 13,
            "optional_int_default": 14,
        }

        expected = OptionalAndDefault(11, None, 13, 14)
        self.assertDeserializesTo(OptionalAndDefault, data, expected)

    def test_skip_int_default(self):
        data = {"int": 11, "optional_int": 12, "optional_int_default": 14}

        expected = OptionalAndDefault(11, 12, 3, 14)
        self.assertDeserializesTo(OptionalAndDefault, data, expected)

    def test_skip_optional_int_default(self):
        data = {
            "int": 11,
            "optional_int": 12,
            "int_default": 13,
        }

        expected = OptionalAndDefault(11, 12, 13, 4)
        self.assertDeserializesTo(OptionalAndDefault, data, expected)

    def test_optional_int_default_none(self):
        data = {
            "int": 11,
            "optional_int": 12,
            "int_default": 13,
            "optional_int_default": None,
        }

        expected = OptionalAndDefault(11, 12, 13, None)
        self.assertDeserializesTo(OptionalAndDefault, data, expected)

    def test_extra(self):
        data = {
            "int": 11,
            "optional_int": 12,
            "int_default": 13,
            "optional_int_default": 14,
            "extra": 15,
        }

        with self.assertRaises(KeyError):
            self.serializer.deserialize(OptionalAndDefault, data)
