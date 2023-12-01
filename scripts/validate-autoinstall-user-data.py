#!/usr/bin/env python3

# Copyright 2022 Canonical, Ltd.
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

""" Entry-point to validate autoinstall-user-data against schema.
By default, we are expecting the autoinstall user-data to be wrapped in a cloud
config format:

#cloud-config
autoinstall:
  <user data comes here>

To validate the user-data directly, you can pass the --no-expect-cloudconfig
switch.
"""

import argparse
import io
import json

import jsonschema
import yaml


def main() -> None:
    """ Entry point. """
    parser = argparse.ArgumentParser()

    parser.add_argument("--json-schema",
                        help="Path to the JSON schema",
                        type=argparse.FileType("r"),
                        default="autoinstall-schema.json")
    parser.add_argument("input", nargs="?",
                        help="Path to the user data instead of stdin",
                        type=argparse.FileType("r"),
                        default="-")
    parser.add_argument("--no-expect-cloudconfig", dest="expect-cloudconfig",
                        action="store_false",
                        help="Assume the data is not wrapped in cloud-config.",
                        default=True)

    args = vars(parser.parse_args())

    user_data: io.TextIOWrapper = args["input"]

    if args["expect-cloudconfig"]:
        assert user_data.readline() == "#cloud-config\n"
        def get_autoinstall_data(data): return data["autoinstall"]
    else:
        def get_autoinstall_data(data): return data

    # Verify autoinstall doc link is in the file

    stream_pos: int = user_data.tell()

    data: str = user_data.read()

    link: str = "https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html"  # noqa: E501

    assert link in data

    # Verify autoinstall schema
    user_data.seek(stream_pos)

    data = yaml.safe_load(user_data)

    jsonschema.validate(get_autoinstall_data(data),
                        json.load(args["json_schema"]))


if __name__ == "__main__":
    main()
