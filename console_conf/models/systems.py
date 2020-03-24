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
import logging
import json

import attr
import jsonschema

log = logging.getLogger("console_conf.models.systems")

# This json schema describes the recovery systems data. Allow additional
# properties at each level so that console-conf does not have to be exactly in
# sync with snapd.
_RECOVERY_SYSTEMS_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "systems",
    "type": "object",
    "additionalProperties": True,
    "required": ["systems"],
    "properties": {
        "systems": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["label", "brand", "model"],
                "properties": {
                    "label": {"type": "string"},
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["title", "mode"],
                            "properties": {
                                "title": {"type": "string"},
                                "mode": {"type": "string"},
                            },
                        },
                    },
                    "brand": {
                        "type": "object",
                        "additionalProperties": True,
                        "required": ["id", "username", "display-name"],
                        "properties": {
                            "id": {"type": "string"},
                            "username": {"type": "string"},
                            "display-name": {"type": "string"},
                            "validation": {"type": "string"},
                        },
                    },
                    "model": {
                        "type": "object",
                        "additionalProperties": True,
                        "required": ["model", "brand-id", "display-name"],
                        "properties": {
                            "model": {"type": "string"},
                            "brand-id": {"type": "string"},
                            "display-name": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}


class RecoverySystemsModel:
    """Recovery chooser data"""

    def __init__(self, systems_data):
        self.systems = systems_data
        # current selection
        self._selection = None

    def select(self, system, action):
        self._selection = SelectedSystemAction(system=system, action=action)

    @property
    def selection(self):
        return self._selection

    @staticmethod
    def from_systems_stream(chooser_input):
        """Deserialize recovery systems from input JSON stream."""
        try:
            dec = json.load(chooser_input)
            jsonschema.validate(dec, _RECOVERY_SYSTEMS_SCHEMA)
            systems = dec.get("systems", [])
        except json.JSONDecodeError:
            log.exception("cannot decode recovery systems info")
            raise
        except jsonschema.ValidationError:
            log.exception("cannot validate recovery systems data")
            raise

        systems = []
        for sys in dec["systems"]:
            m = sys["model"]
            b = sys["brand"]
            model = SystemModel(
                model=m["model"],
                brand_id=m["brand-id"],
                display_name=m["display-name"]
            )
            brand = Brand(
                ID=b["id"],
                username=b["username"],
                display_name=b["display-name"],
                validation=b.get("validation", "unproven"),
            )
            actions = []
            for a in sys.get("actions", []):
                actions.append(SystemAction(title=a["title"], mode=a["mode"]))
            s = RecoverySystem(
                current=sys.get("current", False),
                label=sys["label"],
                model=model,
                brand=brand,
                actions=actions,
            )
            systems.append(s)

        return RecoverySystemsModel(systems)

    @staticmethod
    def to_response_stream(obj, chooser_output):
        """Serialize an object with selected action as JSON to the given output
        stream.
        """
        if not isinstance(obj, SelectedSystemAction):
            raise TypeError("unexpected type: {}".format(type(obj)))

        choice = {
            "label": obj.system.label,
            "mode": obj.action.mode,
        }
        return json.dump(choice, fp=chooser_output)


@attr.s
class RecoverySystem:
    current = attr.ib()
    label = attr.ib()
    model = attr.ib()
    brand = attr.ib()
    actions = attr.ib()

    def __eq__(self, other):
        return self.current == other.current and \
            self.label == other.label and \
            self.model == other.model and \
            self.brand == other.brand and \
            self.actions == other.actions


@attr.s
class Brand:
    ID = attr.ib()
    username = attr.ib()
    display_name = attr.ib()
    validation = attr.ib()

    def __eq__(self, other):
        return self.ID == other.ID and \
            self.username == other.username and \
            self.display_name == other.display_name and \
            self.validation == other.validation


@attr.s
class SystemModel:
    model = attr.ib()
    brand_id = attr.ib()
    display_name = attr.ib()

    def __eq__(self, other):
        return self.model == other.model and \
            self.brand_id == other.brand_id and \
            self.display_name == other.display_name


@attr.s
class SystemAction:
    title = attr.ib()
    mode = attr.ib()

    def __eq__(self, other):
        return self.title == other.title and \
            self.mode == other.mode


@attr.s
class SelectedSystemAction:
    system = attr.ib()
    action = attr.ib()

    def __eq__(self, other):
        return self.system == other.system and \
            self.action == other.action
