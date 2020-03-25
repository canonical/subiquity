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

import copy
import json
import sys

from subiquity.cmd.tui import parse_options
from subiquity.core import Subiquity

base_schema = {
    'type': 'object',
    'properties': {
        'version': {
            'type': 'integer',
            'minumum': 1,
            'maximum': 2,
        },
    },
    'requiredProperties': ['version'],
    'additionalProperties': True,
    }


def make_schema(app):
    schema = copy.deepcopy(base_schema)
    for controller in app.controllers.instances:
        ckey = getattr(controller, 'autoinstall_key', None)
        if ckey is None:
            continue
        cschema = getattr(controller, "autoinstall_schema", None)
        if cschema is None:
            continue
        schema['properties'][ckey] = cschema
    return schema


def main():
    opts = parse_options([])
    opts.dry_run = True
    app = Subiquity(opts, None)
    app.base_model = app.make_model()
    app.controllers.load_all()
    json.dump(make_schema(app), sys.stdout, indent=4)


if __name__ == '__main__':
    sys.exit(main())
