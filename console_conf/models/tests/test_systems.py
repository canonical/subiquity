#!/usr/bin/env python3
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
import unittest
import json
import jsonschema
from io import StringIO

from console_conf.models.systems import (
    RecoverySystemsModel,
    RecoverySystem,
    Brand,
    SystemModel,
    SystemAction,
    SelectedSystemAction,
    )


class RecoverySystemsModelTests(unittest.TestCase):

    reference = {
        "systems": [
            {
                "current": True,
                "label": "1234",
                "brand": {
                    "id": "brand-id",
                    "username": "brand-username",
                    "display-name": "this is my brand",
                    "validation": "verified",
                },
                "model": {
                    "model": "core20-amd64",
                    "brand-id": "brand-id",
                    "display-name": "Core 20 AMD64 system",
                },
                "actions": [
                    {"title": "reinstall", "mode": "install"},
                    {"title": "recover", "mode": "recover"},
                ]
            },
            {
                "label": "other",
                "brand": {
                    "id": "other-brand-id",
                    "username": "other-brand",
                    "display-name": "my brand",
                    "validation": "unproven",
                },
                "model": {
                    "model": "my-brand-box",
                    "brand-id": "other-brand-id",
                    "display-name": "Funky box",
                },
                "actions": [
                    {"title": "reinstall", "mode": "install"},
                ]
            }

        ]
    }

    def test_from_systems_stream_happy(self):
        raw = json.dumps(self.reference)
        systems = RecoverySystemsModel.from_systems_stream(StringIO(raw))
        exp = RecoverySystemsModel([
            RecoverySystem(
                current=True,
                label="1234",
                model=SystemModel(
                    model="core20-amd64",
                    brand_id="brand-id",
                    display_name="Core 20 AMD64 system"),
                brand=Brand(
                    ID="brand-id",
                    username="brand-username",
                    display_name="this is my brand",
                    validation="verified"),
                actions=[SystemAction(title="reinstall", mode="install"),
                         SystemAction(title="recover", mode="recover")]
                ),
            RecoverySystem(
                current=False,
                label="other",
                model=SystemModel(
                    model="my-brand-box",
                    brand_id="other-brand-id",
                    display_name="Funky box"),
                brand=Brand(
                    ID="other-brand-id",
                    username="other-brand",
                    display_name="my brand",
                    validation="unproven"),
                actions=[SystemAction(title="reinstall", mode="install")]
                ),
            ])
        self.assertEqual(systems.systems, exp.systems)
        self.assertEqual(systems.current, exp.systems[0])

    def test_from_systems_stream_invalid_empty(self):
        with self.assertRaises(jsonschema.ValidationError):
            RecoverySystemsModel.from_systems_stream(StringIO("{}"))

    def test_from_systems_stream_invalid_missing_system_label(self):
        raw = json.dumps({
            "systems": [
                {
                    "brand": {
                        "id": "brand-id",
                        "username": "brand-username",
                        "display-name": "this is my brand",
                        "validation": "verified",
                    },
                    "model": {
                        "model": "core20-amd64",
                        "brand-id": "brand-id",
                        "display-name": "Core 20 AMD64 system",
                    },
                    "actions": [
                        {"title": "reinstall", "mode": "install"},
                        {"title": "recover", "mode": "recover"},
                    ]
                },
            ]
        })
        with self.assertRaises(jsonschema.ValidationError):
            RecoverySystemsModel.from_systems_stream(StringIO(raw))

    def test_from_systems_stream_invalid_missing_brand(self):
        raw = json.dumps({
            "systems": [
                {
                    "label": "1234",
                    "model": {
                        "model": "core20-amd64",
                        "brand-id": "brand-id",
                        "display-name": "Core 20 AMD64 system",
                    },
                    "actions": [
                        {"title": "reinstall", "mode": "install"},
                        {"title": "recover", "mode": "recover"},
                    ]
                },
            ]
        })
        with self.assertRaises(jsonschema.ValidationError):
            RecoverySystemsModel.from_systems_stream(StringIO(raw))

    def test_from_systems_stream_invalid_missing_model(self):
        raw = json.dumps({
            "systems": [
                {
                    "label": "1234",
                    "brand": {
                        "id": "brand-id",
                        "username": "brand-username",
                        "display-name": "this is my brand",
                        "validation": "verified",
                    },
                    "actions": [
                        {"title": "reinstall", "mode": "install"},
                        {"title": "recover", "mode": "recover"},
                    ]
                },
            ]
        })
        with self.assertRaises(jsonschema.ValidationError):
            RecoverySystemsModel.from_systems_stream(StringIO(raw))

    def test_from_systems_stream_valid_no_actions(self):
        raw = json.dumps({
            "systems": [
                {
                    "label": "1234",
                    "model": {
                        "model": "core20-amd64",
                        "brand-id": "brand-id",
                        "display-name": "Core 20 AMD64 system",
                    },
                    "brand": {
                        "id": "brand-id",
                        "username": "brand-username",
                        "display-name": "this is my brand",
                        "validation": "verified",
                    },
                    "actions": [],
                },
            ]
        })
        RecoverySystemsModel.from_systems_stream(StringIO(raw))

    def test_selection(self):
        raw = json.dumps(self.reference)
        model = RecoverySystemsModel.from_systems_stream(StringIO(raw))
        model.select(model.systems[1], model.systems[1].actions[0])
        self.assertEqual(model.selection,
                         SelectedSystemAction(
                             system=model.systems[1],
                             action=model.systems[1].actions[0]))
        model.unselect()
        self.assertIsNone(model.selection)

    def test_to_response_stream(self):
        raw = json.dumps(self.reference)
        model = RecoverySystemsModel.from_systems_stream(StringIO(raw))

        model.select(model.systems[1], model.systems[1].actions[0])

        stream = StringIO()
        RecoverySystemsModel.to_response_stream(model.selection, stream)
        fromjson = json.loads(stream.getvalue())
        self.assertEqual(fromjson, {
            "label": "other",
            "action": {
                "mode": "install",
                "title": "reinstall",
                },
            })

    def test_no_current(self):
        reference = {
            "systems": [
                {
                    "current": False,
                    "label": "1234",
                    "brand": {
                        "id": "brand-id",
                        "username": "brand-username",
                        "display-name": "this is my brand",
                        "validation": "verified",
                    },
                    "model": {
                        "model": "core20-amd64",
                        "brand-id": "brand-id",
                        "display-name": "Core 20 AMD64 system",
                    },
                    "actions": [
                        {"title": "reinstall", "mode": "install"},
                        {"title": "recover", "mode": "recover"},
                    ]
                },
            ],
        }
        systems = RecoverySystemsModel.from_systems(reference["systems"])
        self.assertEqual(len(systems.systems), 1)
        self.assertEqual(systems.systems[0].label, "1234")
        self.assertIsNone(systems.current)
