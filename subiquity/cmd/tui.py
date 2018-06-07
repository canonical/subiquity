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
import signal
import sys

from subiquitycore.log import setup_logger
from subiquitycore import __version__ as VERSION
from subiquitycore.core import ApplicationError
from subiquitycore.ui.frame import SubiquityUI
from subiquitycore.utils import environment_check

from subiquity.core import Subiquity


ENVIRONMENT = '''
checks:
    read:
        file:
            - /var/log/syslog
    write:
        directory:
            - /tmp
    mount:
        directory:
            - /proc
            - /sys
    exec:
        file:
            - /sbin/hdparm
            - /usr/bin/curtin
'''


class ClickAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        namespace.scripts.append("c(" + repr(values) + ")")


def parse_options(argv):
    parser = argparse.ArgumentParser(
        description='SUbiquity - Ubiquity for Servers',
        prog='subiquity')
    parser.add_argument('--dry-run', action='store_true',
                        dest='dry_run',
                        help='menu-only, do not call installer function')
    parser.add_argument('--serial', action='store_true',
                        dest='run_on_serial',
                        help='Run the installer over serial console.')
    parser.add_argument('--machine-config', metavar='CONFIG',
                        dest='machine_config',
                        help="Don't Probe. Use probe data file")
    parser.add_argument('--uefi', action='store_true',
                        dest='uefi',
                        help='run in uefi support mode')
    parser.add_argument('--screens', action='append', dest='screens',
                        default=[])
    parser.add_argument('--script', metavar="SCRIPT", action='append',
                        dest='scripts', default=[],
                        help=('Execute SCRIPT in a namespace containing view '
                              'helpers and "ui"'))
    parser.add_argument('--click', metavar="PAT", action=ClickAction,
                        help='Synthesize a click on a button matching PAT')
    parser.add_argument('--answers')
    parser.add_argument('--source', default=[], action='append',
                        dest='sources', metavar='URL',
                        help='install from url instead of default.')
    parser.add_argument(
        '--snaps-from-examples', action='store_true',
        help=("Load snap details from examples/snaps instead of store. "
              "See examples/snaps/README.md for more."))
    parser.add_argument(
        '--snap-section', action='store', default='server',
        help=("Show snaps from this section of the store in the snap "
              "list screen."))
    return parser.parse_args(argv)


LOGDIR = "/var/log/installer/"

AUTO_ANSWERS_FILE = "/subiquity_config/answers.yaml"


def main():
    opts = parse_options(sys.argv[1:])
    global LOGDIR
    if opts.dry_run:
        LOGDIR = ".subiquity"
    LOGFILE = setup_logger(dir=LOGDIR)
    logger = logging.getLogger('subiquity')
    logger.info("Starting SUbiquity v{}".format(VERSION))
    logger.info("Arguments passed: {}".format(sys.argv))

    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGQUIT, signal.SIG_IGN)

    env_ok = environment_check(ENVIRONMENT)
    if env_ok is False and not opts.dry_run:
        print('Failed environment check.  '
              'Check {} for errors.'.format(LOGFILE))
        return 1

    if opts.answers is None and os.path.exists(AUTO_ANSWERS_FILE):
        logger.debug("Autoloading answers from %s", AUTO_ANSWERS_FILE)
        opts.answers = AUTO_ANSWERS_FILE

    ui = SubiquityUI()

    try:
        subiquity_interface = Subiquity(ui, opts)
    except ApplicationError as e:
        logger.exception('Failed to load Subiquity interface')
        print(e)
        return 1

    subiquity_interface.run()


if __name__ == '__main__':
    sys.exit(main())
