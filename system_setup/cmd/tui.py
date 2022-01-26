#!/usr/bin/env python3
# Copyright 2015-2021 Canonical, Ltd.
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

from subiquity.cmd.common import (
    LOGDIR,
    setup_environment,
    )
from system_setup.cmd.server import make_server_args_parser


class ClickAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        namespace.scripts.append("c(" + repr(values) + ")")


def make_client_args_parser():
    # TODO WSL: update this. We have already done it on the past…
    parser = argparse.ArgumentParser(
        description='SUbiquity - Ubiquity for Servers',
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
    parser.add_argument('--answers')
    parser.add_argument('--server-pid')
    parser.add_argument('--prefill',
                        dest='prefill',
                        help='Prefills UI models with data provided in'
                        ' a prefill.yaml file yet allowing overrides.')
    parser.add_argument('--output-base', action='store', dest='output_base',
                        default='.subiquity',
                        help='in dryrun, control basedir of files')
    return parser


AUTO_ANSWERS_FILE = "/subiquity_config/answers.yaml"


def main():
    setup_environment()
    # setup_environment sets $APPORT_DATA_DIR which must be set before
    # apport is imported, which is done by this import:
    from system_setup.client.client import SystemSetupClient
    parser = make_client_args_parser()
    args = sys.argv[1:]

    need_start_server = False
    server_args = []
    server_output_dir = "/var/log/installer"
    server_state_file = "/run/subiquity/server-state"
    opts, unknown = parser.parse_known_args(args)
    if '--dry-run' in args:
        server_state_file = opts.output_base + "/run/subiquity/server-state"
        if opts.socket is None:
            need_start_server = True
            server_output_dir = opts.output_base
            sock_path = os.path.join(server_output_dir, 'socket')
            opts.socket = sock_path
            server_args = ['--dry-run', '--socket=' + sock_path] + unknown

    elif opts.socket is None:
        need_start_server = True
        opts.socket = '/run/subiquity/socket'

    if opts.prefill:
        server_args += ['--prefill='+opts.prefill]

    os.makedirs(server_output_dir, exist_ok=True)
    server_output = open(os.path.join(server_output_dir, 'server-output'), 'w')

    if need_start_server:
        if os.path.exists(server_state_file):
            os.unlink(server_state_file)
        server_parser = make_server_args_parser()
        server_parser.parse_args(server_args)  # just to check
        server_cmd = [sys.executable, '-m', 'system_setup.cmd.server'] + \
            server_args
        server_proc = subprocess.Popen(
            server_cmd, stdout=server_output, stderr=subprocess.STDOUT)
        opts.server_pid = str(server_proc.pid)
        print("running server pid {} with args: {}"
              .format(server_proc.pid, server_cmd))
    elif opts.server_pid is not None:
        print("reconnecting to server pid {}".format(opts.server_pid))

    os.makedirs(os.path.basename(opts.socket), exist_ok=True)
    logdir = LOGDIR
    if opts.dry_run:
        logdir = opts.output_base
    logfiles = setup_logger(dir=logdir, base='systemsetup-client')

    logger = logging.getLogger('subiquity')
    version = "unknown"
    logger.info("Starting System Setup revision {}".format(version))
    logger.info("Arguments passed: {}".format(sys.argv))

    opts.ssh = False
    opts.screens = []
    opts.scripts = []
    opts.run_on_serial = False
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

    subiquity_interface = SystemSetupClient(opts)

    subiquity_interface.note_file_for_apport(
        "InstallerLog", logfiles['debug'])
    subiquity_interface.note_file_for_apport(
        "InstallerLogInfo", logfiles['info'])

    subiquity_interface.run()


if __name__ == '__main__':
    sys.exit(main())
