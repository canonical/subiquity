# Copyright 2020-2021 Canonical, Ltd.
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
import sys

from subiquity.cmd.common import LOGDIR, setup_environment
from subiquitycore.log import setup_logger


def make_server_args_parser():
    parser = argparse.ArgumentParser(
        description="System Setup - Initial Boot Setup", prog="system_setup"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="menu-only, do not call installer function",
    )
    parser.add_argument("--socket")
    parser.add_argument("--autoinstall", action="store")
    parser.add_argument(
        "--prefill",
        dest="prefill",
        help="Prefills UI models with data provided in"
        " a prefill.yaml file yet allowing overrides.",
    )
    parser.add_argument(
        "--output-base",
        action="store",
        dest="output_base",
        default=".subiquity",
        help="in dryrun, control basedir of files",
    )
    parser.add_argument(
        "--tcp-port",
        dest="tcp_port",
        type=int,
        choices=range(49152, 60999),
        metavar="[49152 to 60999]",
        help="The TCP port Subiquity must listen to. It means "
        "TCP will be used instead of Unix domain sockets. "
        "Only localhost connections are accepted.",
    )
    return parser


def main():
    print("starting server")
    setup_environment()
    # setup_environment sets $APPORT_DATA_DIR which must be set before
    # apport is imported, which is done by this import:
    from subiquity.server.server import NOPROBERARG
    from system_setup.server.server import SystemSetupServer

    parser = make_server_args_parser()
    opts = parser.parse_args(sys.argv[1:])
    logdir = LOGDIR
    opts.snaps_from_examples = False
    opts.kernel_cmdline = {}
    opts.machine_config = NOPROBERARG
    if opts.dry_run:
        logdir = opts.output_base
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

    logfiles = setup_logger(dir=logdir, base="systemsetup-server")

    logger = logging.getLogger("systemsetup-server")
    version = "unknown"
    logger.info("Starting System Setup server revision {}".format(version))
    logger.info("Arguments passed: {}".format(sys.argv))

    prefillFile = opts.prefill
    if prefillFile:
        if not os.path.isfile(prefillFile):
            logger.error(
                '"File {}" is invalid. Option will be ignored.'.format(prefillFile)
            )
            opts.prefill = None

    async def run_with_loop():
        server = SystemSetupServer(opts, block_log_dir)
        server.note_file_for_apport("InstallerServerLog", logfiles["debug"])
        server.note_file_for_apport("InstallerServerLogInfo", logfiles["info"])
        await server.run()

    asyncio.run(run_with_loop())


if __name__ == "__main__":
    sys.exit(main())
