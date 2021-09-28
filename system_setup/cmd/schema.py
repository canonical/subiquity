#!/usr/bin/env python3
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

import json
import sys

import jsonschema

from system_setup.cmd.server import make_server_args_parser
from system_setup.server.server import SystemSetupServer
from subiquity.cmd.schema import make_schema
from subiquity.server.server import NOPROBERARG


def make_app():
    parser = make_server_args_parser()
    opts, unknown = parser.parse_known_args(['--dry-run'])
    opts.machine_config = NOPROBERARG
    opts.kernel_cmdline = ""
    opts.snaps_from_examples = False
    app = SystemSetupServer(opts, '')
    app.base_model = app.make_model()
    app.controllers.load_all()
    return app


def main():
    schema = make_schema(make_app())
    jsonschema.validate({"version": 1}, schema)
    print(json.dumps(schema, indent=4))


if __name__ == '__main__':
    sys.exit(main())
