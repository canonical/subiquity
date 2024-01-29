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
from textwrap import dedent
from typing import Callable
import json

import jsonschema
import yaml


def parse_args() -> argparse.Namespace:
    """Parse arguments with argparse"""

    description: str = dedent(
        """\
    Validate autoinstall user data against the autoinstall schema. By default
    expects the user data is wrapped in a cloud-config. Example:

    #cloud-config
    autoinstall:
        <user data here>

    To validate the user data directly, you can pass --no-expect-cloudconfig
    """
    )

    parser = argparse.ArgumentParser(
        prog="validate-autoinstall-user-data",
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--json-schema",
        help="Path to the JSON schema",
        type=argparse.FileType("r"),
        default="autoinstall-schema.json",
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to the user data instead of stdin",
        type=argparse.FileType("r"),
        default="-",
    )
    parser.add_argument(
        "--no-expect-cloudconfig",
        dest="expect_cloudconfig",
        action="store_false",
        help="Assume the data is not wrapped in cloud-config.",
        default=True,
    )
    parser.add_argument(
        "--check-link",
        dest="check_link",
        action="store_true",
        help="Assert the documentation link is in the user data",
        default=False,
    )

    args: argparse.Namespace = parser.parse_args()

    return args


def get_autoinstall_no_cloudconfig(data: dict):
    if "autoinstall" in data:
        raise AssertionError("Expected no cloud-config but found key 'autoinstall'")
    return data


def get_autoinstall_with_cloudconfig(data: dict):
    if "autoinstall" not in data:
        raise AssertionError("Missing key 'autoinstall'")

    return data["autoinstall"]


def main() -> None:
    """Entry point."""

    args: argparse.Namespace = parse_args()

    user_data: io.TextIOWrapper = args.input
    str_data: str = user_data.read()

    # Verify autoinstall doc link is in the file
    if args.check_link:
        link: str = "https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html"  # noqa: E501

        if link not in str_data:
            raise AssertionError("Documentation link missing from user data")

    if args.expect_cloudconfig:
        first_line: str = str_data.splitlines()[0]
        if not first_line == "#cloud-config":
            raise AssertionError(
                (
                    "Expected data to be wrapped in cloud-config "
                    "but first line is not '#cloud-config'. Try "
                    "passing --no-expect-cloudconfig."
                )
            )

        get_autoinstall_data: Callable[[dict], dict] = get_autoinstall_with_cloudconfig

    else:
        get_autoinstall_data: Callable[[dict], dict] = get_autoinstall_no_cloudconfig

    # Verify autoinstall schema
    yaml_data: dict = yaml.safe_load(str_data)

    jsonschema.validate(get_autoinstall_data(yaml_data), json.load(args.json_schema))


if __name__ == "__main__":
    main()
