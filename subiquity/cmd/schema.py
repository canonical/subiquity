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

import jsonschema

from subiquity.cmd.tui import make_client_args_parser
from subiquity.cmd.server import make_server_args_parser
from subiquity.client.client import SubiquityClient
from subiquity.server.server import SubiquityServer


def make_schema(server, client):
    schema = copy.deepcopy(server.base_schema)
    instances = server.controllers.instances + client.controllers.instances
    for controller in instances:
        ckey = getattr(controller, 'autoinstall_key', None)
        if ckey is None:
            continue
        cschema = getattr(controller, "autoinstall_schema", None)
        if cschema is None:
            continue
        schema['properties'][ckey] = cschema
    return schema


def make(server):
    if server:
        parser = make_server_args_parser()
    else:
        parser = make_client_args_parser()
    args = []
    opts, unknown = parser.parse_known_args(args)
    opts.dry_run = True
    if server:
        result = SubiquityServer(opts, '')
    else:
        result = SubiquityClient(opts)
    result.base_model = result.make_model()
    result.controllers.load_all()
    return result


def make_client():
    return make(False)


def make_server():
    return make(True)


def main():
    schema = make_schema(make_server(), make_client())
    jsonschema.validate({"version": 1}, schema)
    print(json.dumps(schema, indent=4))


if __name__ == '__main__':
    sys.exit(main())
