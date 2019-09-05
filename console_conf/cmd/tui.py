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
import sys
import logging
from subiquitycore.log import setup_logger
from subiquitycore import __version__ as VERSION
from console_conf.core import ConsoleConf
from subiquitycore.core import ApplicationError
from subiquitycore.utils import environment_check


# Does console-conf actually need any of this?
ENVIRONMENT = '''
checks:
    write:
        directory:
            - /tmp
    mount:
        directory:
            - /proc
            - /sys
'''


class ClickAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        namespace.scripts.append("c(" + repr(values) + ")")


def parse_options(argv):
    parser = argparse.ArgumentParser(
        description=(
            'console-conf - Pre-Ownership Configuration for Ubuntu Core'),
        prog='console-conf')
    parser.add_argument('--dry-run', action='store_true',
                        dest='dry_run',
                        help='menu-only, do not call installer function')
    parser.add_argument('--serial', action='store_true',
                        dest='run_on_serial',
                        help='Run the installer over serial console.')
    parser.add_argument('--machine-config', metavar='CONFIG',
                        dest='machine_config',
                        help="Don't Probe. Use probe data file")
    parser.add_argument('--screens', action='append', dest='screens',
                        default=[])
    parser.add_argument('--script', metavar="SCRIPT", action='append',
                        dest='scripts', default=[],
                        help=('Execute SCRIPT in a namespace containing view '
                              'helpers and "ui"'))
    parser.add_argument('--click', metavar="PAT", action=ClickAction,
                        help='Synthesize a click on a button matching PAT')
    parser.add_argument('--answers')
    return parser.parse_args(argv)


LOGDIR = "/var/log/console-conf/"


def main():
    opts = parse_options(sys.argv[1:])
    global LOGDIR
    if opts.dry_run:
        LOGDIR = ".subiquity"
    LOGFILE = setup_logger(dir=LOGDIR)
    logger = logging.getLogger('console_conf')
    logger.info("Starting console-conf v{}".format(VERSION))
    logger.info("Arguments passed: {}".format(sys.argv))

    env_ok = environment_check(ENVIRONMENT)
    if env_ok is False and not opts.dry_run:
        print('Failed environment check.  '
              'Check {} for errors.'.format(LOGFILE))
        return 1

    try:
        interface = ConsoleConf(opts)
    except ApplicationError as e:
        logger.exception('Failed to load ConsoleConf interface')
        print(e)
        return 1

    interface.run()


if __name__ == '__main__':
    sys.exit(main())
