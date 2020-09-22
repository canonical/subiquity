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
import logging
import os
import sys

from subiquitycore.log import setup_logger

from .common import (
    LOGDIR,
    setup_environment,
    )


def make_server_args_parser():
    parser = argparse.ArgumentParser(
        description='SUbiquity - Ubiquity for Servers',
        prog='subiquity')
    parser.add_argument('--dry-run', action='store_true',
                        dest='dry_run',
                        help='menu-only, do not call installer function')
    parser.add_argument('--socket')
    return parser


def main():
    print('starting server')
    setup_environment()
    # setup_environment sets $APPORT_DATA_DIR which must be set before
    # apport is imported, which is done by this import:
    from subiquity.server.server import SubiquityServer
    parser = make_server_args_parser()
    opts = parser.parse_args(sys.argv[1:])
    logdir = LOGDIR
    if opts.dry_run:
        logdir = ".subiquity"
    if opts.socket is None:
        if opts.dry_run:
            opts.socket = '.subiquity/socket'
        else:
            opts.socket = '/run/subiquity/socket'
    os.makedirs(os.path.basename(opts.socket), exist_ok=True)

    logfiles = setup_logger(dir=logdir, base='subiquity-server')

    logger = logging.getLogger('subiquity')
    version = os.environ.get("SNAP_REVISION", "unknown")
    logger.info("Starting Subiquity server revision {}".format(version))
    logger.info("Arguments passed: {}".format(sys.argv))

    subiquity_interface = SubiquityServer(opts)

    subiquity_interface.note_file_for_apport(
        "InstallerServerLog", logfiles['debug'])
    subiquity_interface.note_file_for_apport(
        "InstallerServerLogInfo", logfiles['info'])

    subiquity_interface.run()


if __name__ == '__main__':
    sys.exit(main())
