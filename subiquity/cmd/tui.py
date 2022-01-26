#!/usr/bin/env python3
# Copyright 2015 Canonical, Ltd.
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
import fcntl
import subprocess
import sys

from subiquitycore.log import setup_logger

from .common import (
    LOGDIR,
    setup_environment,
    )
from .server import make_server_args_parser


class ClickAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        namespace.scripts.append("c(" + repr(values) + ")")


def make_client_args_parser():
    parser = argparse.ArgumentParser(
        description='Subiquity - Ubiquity for Servers',
        prog='subiquity')
    try:
        ascii_default = os.ttyname(0) == "/dev/ttysclp0"
    except OSError:
        ascii_default = False
    parser.set_defaults(ascii=ascii_default)
    parser.add_argument('--dry-run', action='store_true',
                        dest='dry_run',
                        help='menu-only, do not call installer function')
    parser.add_argument('--socket')
    parser.add_argument('--serial', action='store_true',
                        dest='run_on_serial',
                        help='Run the installer over serial console.')
    parser.add_argument('--ssh', action='store_true',
                        dest='ssh',
                        help='Print ssh login details')
    parser.add_argument('--ascii', action='store_true',
                        dest='ascii',
                        help='Run the installer in ascii mode.')
    parser.add_argument('--unicode', action='store_false',
                        dest='ascii',
                        help='Run the installer in unicode mode.')
    parser.add_argument('--screens', action='append', dest='screens',
                        default=[])
    parser.add_argument('--script', metavar="SCRIPT", action='append',
                        dest='scripts', default=[],
                        help=('Execute SCRIPT in a namespace containing view '
                              'helpers and "ui"'))
    parser.add_argument('--click', metavar="PAT", action=ClickAction,
                        help='Synthesize a click on a button matching PAT')
    parser.add_argument('--answers')
    parser.add_argument('--server-pid')
    parser.add_argument('--output-base', action='store', dest='output_base',
                        default='.subiquity',
                        help='in dryrun, control basedir of files')
    return parser


AUTO_ANSWERS_FILE = "/subiquity_config/answers.yaml"


def main():
    setup_environment()
    # setup_environment sets $APPORT_DATA_DIR which must be set before
    # apport is imported, which is done by this import:
    from subiquity.client.client import SubiquityClient
    parser = make_client_args_parser()
    args = sys.argv[1:]
    if '--dry-run' in args:
        opts, unknown = parser.parse_known_args(args)
        if opts.socket is None:
            base = opts.output_base
            os.makedirs(base, exist_ok=True)
            if os.path.exists(f'{base}/run/subiquity/server-state'):
                os.unlink(f'{base}/run/subiquity/server-state')
            sock_path = base + '/socket'
            opts.socket = sock_path
            server_args = ['--dry-run', '--socket=' + sock_path] + unknown
            server_args.extend(('--output-base', base))
            server_parser = make_server_args_parser()
            server_parser.parse_args(server_args)  # just to check
            server_output = open(base + '/server-output', 'w')
            server_cmd = [sys.executable, '-m', 'subiquity.cmd.server'] + \
                server_args
            server_proc = subprocess.Popen(
                server_cmd, stdout=server_output, stderr=subprocess.STDOUT)
            opts.server_pid = str(server_proc.pid)
            print("running server pid {}".format(server_proc.pid))
        elif opts.server_pid is not None:
            print("reconnecting to server pid {}".format(opts.server_pid))
        else:
            opts = parser.parse_args(args)
    else:
        opts = parser.parse_args(args)
        if opts.socket is None:
            opts.socket = '/run/subiquity/socket'
    os.makedirs(os.path.basename(opts.socket), exist_ok=True)
    logdir = LOGDIR
    if opts.dry_run:
        logdir = opts.output_base
    logfiles = setup_logger(dir=logdir, base='subiquity-client')

    logger = logging.getLogger('subiquity')
    version = os.environ.get("SNAP_REVISION", "unknown")
    logger.info("Starting Subiquity revision {}".format(version))
    logger.info("Arguments passed: {}".format(sys.argv))

    if opts.answers is None and os.path.exists(AUTO_ANSWERS_FILE):
        logger.debug("Autoloading answers from %s", AUTO_ANSWERS_FILE)
        opts.answers = AUTO_ANSWERS_FILE

    if opts.answers:
        opts.answers = open(opts.answers)
        try:
            fcntl.flock(opts.answers, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            logger.exception(
                'Failed to lock auto answers file, proceding without it.')
            opts.answers.close()
            opts.answers = None

    subiquity_interface = SubiquityClient(opts)

    subiquity_interface.note_file_for_apport(
        "InstallerLog", logfiles['debug'])
    subiquity_interface.note_file_for_apport(
        "InstallerLogInfo", logfiles['info'])

    subiquity_interface.run()


if __name__ == '__main__':
    sys.exit(main())
