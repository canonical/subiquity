#!/usr/bin/env python3

# Copyright 2022 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Validate autoinstall-user-data against the autoinstall schema.

By default, we are expecting the autoinstall user-data to be wrapped in a cloud
config format. Example:

    #cloud-config
    autoinstall:
      <user data comes here>

To validate the user-data directly, you can pass the --no-expect-cloudconfig
switch.
"""

import argparse
import asyncio
import io
import json
import os
import sys
import tempfile
import traceback
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Any

import jsonschema
import yaml

# Python path trickery so we can import subiquity code and still call this
# script without using the makefile. Eventually we should ship this a
# program in the subiquity snap, so users don't even have to checkout the
# source code but that will also require work to make sure Subiquity is
# safe to install on regular systems.
scripts_dir = sys.path[0]
subiquity_root = Path(scripts_dir) / ".."
curtin_root = subiquity_root / "curtin"
probert_root = subiquity_root / "probert"

sys.path.insert(0, str(subiquity_root))
sys.path.insert(1, str(curtin_root))
sys.path.insert(2, str(probert_root))

os.environ["SNAP"] = str(subiquity_root)

from subiquity.cmd.server import make_server_args_parser  # noqa: E402
from subiquity.server.dryrun import DRConfig  # noqa: E402
from subiquity.server.server import SubiquityServer  # noqa: E402

DOC_LINK: str = (
    "https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html"  # noqa: E501
)


SUCCESS_MSG: str = "Success: The provided autoinstall config validated successfully"
FAILURE_MSG: str = "Failure: The provided autoinstall config failed validation"


def verify_link(data: str) -> bool:
    """Verify the autoinstall doc link is in the generated user-data."""

    return DOC_LINK in data


def parse_cloud_config(data: str) -> dict[str, Any]:
    """Parse cloud-config and extra autoinstall data."""

    # "#cloud-config" header is required for cloud-config data
    first_line: str = data.splitlines()[0]
    if not first_line == "#cloud-config":
        raise AssertionError(
            (
                "Expected data to be wrapped in cloud-config "
                "but first line is not '#cloud-config'. Try "
                "passing --no-expect-cloudconfig."
            )
        )

    cc_data: dict[str, Any] = yaml.safe_load(data)

    # "autoinstall" top-level keyword is required in cloud-config delivery case
    if "autoinstall" not in cc_data:
        raise AssertionError(
            (
                "Expected data to be wrapped in cloud-config "
                "but could not find top level 'autoinstall' "
                "key."
            )
        )
    else:
        return cc_data["autoinstall"]


def parse_autoinstall(user_data: str, expect_cloudconfig: bool) -> dict[str, Any]:
    """Parse stringified user_data and extract autoinstall data."""

    if expect_cloudconfig:
        return parse_cloud_config(user_data)
    else:
        return yaml.safe_load(user_data)


def legacy_verify(ai_data: dict[str, Any], json_schema: io.TextIOWrapper) -> None:
    """Legacy verification method for use in CI"""

    # support top-level "autoinstall" in regular autoinstall user data
    if "autoinstall" in ai_data:
        data: dict[str, Any] = ai_data["autoinstall"]
    else:
        data: dict[str, Any] = ai_data

    jsonschema.validate(data, json.load(json_schema))


async def make_app() -> SubiquityServer:
    parser: ArgumentParser = make_server_args_parser()
    opts, unknown = parser.parse_known_args(["--dry-run"])
    app: SubiquityServer = SubiquityServer(opts, "")
    # This is needed because the ubuntu-pro server controller accesses dr_cfg
    # in the initializer.
    app.dr_cfg = DRConfig()
    app.base_model = app.make_model()
    app.controllers.load_all()
    return app


async def verify_autoinstall(
    app: SubiquityServer,
    cfg_path: str,
    verbosity: int = 0,
) -> int:
    """Verify autoinstall configuration using a SubiquityServer.

    Returns 0 if successfully validated.
    Returns 1 if fails to validate.
    """

    # Tell the server where to load the autoinstall
    app.autoinstall = cfg_path

    # Suppress start and finish events unless verbosity >=2
    if verbosity < 2:
        for el in app.event_listeners:
            el.report_start_event = lambda x, y: None
            el.report_finish_event = lambda x, y, z: None
    # Suppress info events unless verbosity >=1
    if verbosity < 1:
        for el in app.event_listeners:
            el.report_info_event = lambda x, y: None

    # Make sure all events are printed (we could fail during read, which
    # would happen before we setup the reporting controller)
    app.controllers.Reporting.config = {"builtin": {"type": "print"}}
    app.controllers.Reporting.start()

    # Validation happens during load phases. Do both phases.
    try:
        app.load_autoinstall_config(only_early=True, context=None)
        app.load_autoinstall_config(only_early=False, context=None)
    except Exception as exc:

        print(exc)  # Has the useful error message

        # Print the full traceback if verbosity > 2
        if verbosity > 2:
            traceback.print_exception(exc)

        print(FAILURE_MSG)
        return 1

    print(SUCCESS_MSG)
    return 0


async def _async_main(ai_user_data: dict[str, Any], args: Namespace) -> int:
    # Make a dry-run server
    app: SubiquityServer = await make_app()

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "autoinstall.yaml"
        yaml_as_text: str = yaml.dump(ai_user_data)
        path.write_text(yaml_as_text)

        return await verify_autoinstall(
            app=app,
            cfg_path=path,
            verbosity=args.verbosity,
        )


def parse_args() -> Namespace:
    """Parse argparse arguments."""

    parser = argparse.ArgumentParser(
        prog="validate-autoinstall-user-data",
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
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

    # Hidden validation path we use in CI until the new validation method
    # is ready. i.e. continue to validate based on the json schema directly.
    parser.add_argument(
        "--json-schema",
        help=argparse.SUPPRESS,
        type=argparse.FileType("r"),
        default="autoinstall-schema.json",
    )

    parser.add_argument(
        "--legacy",
        action="store_true",
        help=argparse.SUPPRESS,
        default=False,
    )

    # An option we use in CI to make sure Subiquity will insert a link to
    # the documentation in the auto-generated autoinstall file post-install.
    # There's not need for users to check this.
    parser.add_argument(
        "--check-link",
        dest="check_link",
        action="store_true",
        help=argparse.SUPPRESS,
        default=False,
    )
    parser.add_argument(
        "-v",
        "--verbosity",
        action="count",
        help=(
            "Increase output verbosity. Use -v for more info, -vv for "
            "detailed output, and -vvv for fully detailed output."
        ),
        default=0,
    )

    return parser.parse_args()


def main() -> int:
    """Entry point."""

    args: Namespace = parse_args()

    str_user_data: str = args.input.read()

    # Verify autoinstall doc link is in the file

    if args.check_link:

        assert verify_link(str_user_data), "Documentation link missing from user data"

    # Verify autoinstall schema

    try:
        ai_user_data: dict[str, Any] = parse_autoinstall(
            str_user_data, args.expect_cloudconfig
        )
    except Exception as exc:
        print(f"FAILURE: {exc}")
        return 1

    if args.legacy:
        legacy_verify(ai_user_data, args.json_schema)
        print(SUCCESS_MSG)
        return 0

    return asyncio.run(_async_main(ai_user_data, args))


if __name__ == "__main__":
    sys.exit(main())
