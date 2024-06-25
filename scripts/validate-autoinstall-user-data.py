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
import asyncio
import io
import sys
import tempfile
import traceback
from argparse import Namespace
from pathlib import Path
from textwrap import dedent
from typing import Any

import yaml

# Python path trickery so we can import subiquity code and still call this
# script without using the makefile
scripts_dir = sys.path[0]
subiquity_root = Path(scripts_dir) / ".."
curtin_root = subiquity_root / "curtin"
probert_root = subiquity_root / "probert"
# At the very least, local curtin needs to be in the front of the python path
sys.path.insert(0, str(subiquity_root))
sys.path.insert(1, str(curtin_root))
sys.path.insert(2, str(probert_root))

from subiquity.cmd.server import make_server_args_parser  # noqa: E402
from subiquity.server.dryrun import DRConfig  # noqa: E402
from subiquity.server.server import SubiquityServer  # noqa: E402

SUCCESS_MSG = "Success: The provided autoinstall config validated successfully"
FAILURE_MSG = "Failure: The provided autoinstall config failed validation"


def parse_args() -> Namespace:
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
        "input",
        help="Path to the autoinstall configuration instead of stdin",
        nargs="?",
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
        "-v",
        "--verbosity",
        action="count",
        help=(
            "Increase output verbosity. Use -v for more info, -vv for "
            "detailed output, and -vvv for fully detailed output."
        ),
        default=0,
    )
    # An option we use in CI to make sure Subiquity will insert a link to
    # the documentation in the auto-generated autoinstall file post-install
    parser.add_argument(
        "--check-link",
        dest="check_link",
        action="store_true",
        help=argparse.SUPPRESS,
        default=False,
    )

    return parser.parse_args()


def make_app():
    parser = make_server_args_parser()
    opts, unknown = parser.parse_known_args(["--dry-run"])
    app = SubiquityServer(opts, "")
    # This is needed because the ubuntu-pro server controller accesses dr_cfg
    # in the initializer.
    app.dr_cfg = DRConfig()
    app.base_model = app.make_model()
    app.controllers.load_all()
    return app


def parse_cloud_config(data: str) -> dict[str, Any]:
    """Parse cloud-config and extract autoinstall"""

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


async def verify_autoinstall(cfg_path: str, verbosity: int = 0) -> int:
    """Verify autoinstall configuration.

    Returns 0 if succesfully validated.
    Returns 1 if fails to validate.
    """

    # Make a dry-run server
    app = make_app()

    # Supress start and finish events unless verbosity >=2
    if verbosity < 2:
        for el in app.event_listeners:
            el.report_start_event = lambda x, y: None
            el.report_finish_event = lambda x, y, z: None
    # Suppress info events unless verbosity >=1
    if verbosity < 1:
        for el in app.event_listeners:
            el.report_info_event = lambda x, y: None

    # Tell the server where to load the autoinstall
    app.autoinstall = cfg_path
    # Make sure events are printed (we could fail during read, which
    # would happen before we setup the reporting controller)
    app.controllers.Reporting.config = {"builtin": {"type": "print"}}
    app.controllers.Reporting.start()
    # Do both validation phases
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


def main() -> int:
    """Entry point."""

    args: Namespace = parse_args()

    user_data: io.TextIOWrapper = args.input
    str_data: str = user_data.read()

    # Verify autoinstall doc link is in the file
    if args.check_link:
        link: str = (
            "https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html"  # noqa: E501
        )

        assert link in str_data, "Documentation link missing from user data"

    # Parse out the autoinstall if expected within cloud-config
    if args.expect_cloudconfig:
        try:
            ai_dict: dict[str, Any] = parse_cloud_config(str_data)
        except Exception as exc:
            print(f"{type(exc).__name__}: {exc}")
            print(FAILURE_MSG)
            return 1

        ai_data: str = yaml.dump(ai_dict)
    else:
        ai_data = str_data

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "autoinstall.yaml"
        path.write_text(ai_data)

        return asyncio.run(verify_autoinstall(path, verbosity=args.verbosity))


if __name__ == "__main__":
    sys.exit(main())
