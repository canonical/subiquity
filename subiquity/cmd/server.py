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

import argparse
import asyncio
import logging
import os
import pathlib
import shlex
import sys

import attr

from subiquitycore.log import setup_logger

from .common import LOGDIR, setup_environment


@attr.s(auto_attribs=True)
class CommandLineParams:
    _raw: str
    _tokens: set = attr.Factory(set)
    _values: dict = attr.Factory(dict)

    @classmethod
    def from_cmdline(cls, cmdline):
        r = cls(cmdline)
        for tok in shlex.split(cmdline):
            if "=" in tok:
                k, v = tok.split("=", 1)
                r._values[k] = v
            else:
                r._tokens.add(tok)
        return r

    def __contains__(self, item):
        return item in self._tokens

    def get(self, key, default=None):
        return self._values.get(key, default)


def make_server_args_parser():
    parser = argparse.ArgumentParser(
        description="SUbiquity - Ubiquity for Servers", prog="subiquity"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="menu-only, do not call installer function",
    )
    parser.add_argument("--dry-run-config", type=argparse.FileType())
    parser.add_argument("--socket")
    parser.add_argument(
        "--machine-config",
        metavar="CONFIG",
        dest="machine_config",
        type=argparse.FileType(),
        help="Don't Probe. Use probe data file",
    )
    parser.add_argument(
        "--bootloader",
        choices=["none", "bios", "prep", "uefi"],
        help="Override style of bootloader to use",
    )
    parser.add_argument(
        "--autoinstall",
        action="store",
        help=(
            "Path to autoinstall file. Empty value disables autoinstall. "
            "By default tries to load /autoinstall.yaml, "
            "or autoinstall data from cloud-init."
        ),
    )
    with open("/proc/cmdline") as fp:
        cmdline = fp.read()
    parser.add_argument(
        "--kernel-cmdline",
        action="store",
        default=cmdline,
        type=CommandLineParams.from_cmdline,
    )
    parser.add_argument(
        "--snaps-from-examples",
        action="store_const",
        const=True,
        dest="snaps_from_examples",
        help=(
            "Load snap details from examples/snaps instead of store. "
            "Default in dry-run mode.  "
            "See examples/snaps/README.md for more."
        ),
    )
    parser.add_argument(
        "--no-snaps-from-examples",
        action="store_const",
        const=False,
        dest="snaps_from_examples",
        help=(
            "Load snap details from store instead of examples. "
            "Default in when not in dry-run mode.  "
            "See examples/snaps/README.md for more."
        ),
    )
    parser.add_argument(
        "--snap-section",
        action="store",
        default="server",
        help=("Show snaps from this section of the store in the snap " "list screen."),
    )
    parser.add_argument("--source-catalog", dest="source_catalog", action="store")
    parser.add_argument(
        "--output-base",
        action="store",
        dest="output_base",
        default=".subiquity",
        help="in dryrun, control basedir of files",
    )
    parser.add_argument("--storage-version", action="store", type=int)
    parser.add_argument("--use-os-prober", action="store_true", default=False)
    parser.add_argument(
        "--postinst-hooks-dir", default="/etc/subiquity/postinst.d", type=pathlib.Path
    )
    return parser


def main():
    print("starting server")
    setup_environment()
    # setup_environment sets $APPORT_DATA_DIR which must be set before
    # apport is imported, which is done by this import:
    from subiquity.server.dryrun import DRConfig
    from subiquity.server.server import SubiquityServer

    parser = make_server_args_parser()
    opts = parser.parse_args(sys.argv[1:])
    if opts.storage_version is None:
        opts.storage_version = int(
            opts.kernel_cmdline.get("subiquity-storage-version", 1)
        )
    logdir = LOGDIR
    if opts.dry_run:
        if opts.dry_run_config:
            dr_cfg = DRConfig.load(opts.dry_run_config)
        else:
            dr_cfg = DRConfig()

        if opts.snaps_from_examples is None:
            opts.snaps_from_examples = True
        logdir = opts.output_base
    else:
        dr_cfg = None
    if opts.socket is None:
        if opts.dry_run:
            opts.socket = opts.output_base + "/socket"
        else:
            opts.socket = "/run/subiquity/socket"
    os.makedirs(os.path.dirname(opts.socket), exist_ok=True)

    block_log_dir = os.path.join(logdir, "block")
    os.makedirs(block_log_dir, exist_ok=True)
    handler = logging.FileHandler(os.path.join(block_log_dir, "discover.log"))
    handler.setLevel("DEBUG")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s:%(lineno)d %(message)s")
    )
    logging.getLogger("probert").addHandler(handler)
    handler.addFilter(lambda rec: rec.name != "probert.network")
    logging.getLogger("curtin").addHandler(handler)
    logging.getLogger("block-discover").addHandler(handler)

    logfiles = setup_logger(dir=logdir, base="subiquity-server")

    logger = logging.getLogger("subiquity")
    version = os.environ.get("SNAP_REVISION", "unknown")
    snap = os.environ.get("SNAP", "unknown")
    logger.info(f"Starting Subiquity server revision {version} of snap {snap}")
    logger.info(f"Arguments passed: {sys.argv}")
    logger.debug(f"Kernel commandline: {opts.kernel_cmdline}")
    logger.debug(f"Environment: {os.environ}")

    async def run_with_loop():
        server = SubiquityServer(opts, block_log_dir)
        server.dr_cfg = dr_cfg
        server.note_file_for_apport("InstallerServerLog", logfiles["debug"])
        server.note_file_for_apport("InstallerServerLogInfo", logfiles["info"])
        server.note_file_for_apport(
            "UdiLog",
            os.path.realpath("/var/log/installer/ubuntu_desktop_installer.log"),
        )
        await server.run()

    asyncio.run(run_with_loop())


if __name__ == "__main__":
    sys.exit(main())
