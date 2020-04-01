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
import sys
import time

from cloudinit import atomic_helper, safeyaml, stages

from subiquitycore.log import setup_logger
from subiquitycore.utils import run_command

from subiquity.core import Subiquity


class ClickAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        namespace.scripts.append("c(" + repr(values) + ")")


def parse_options(argv):
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
    parser.add_argument('--serial', action='store_true',
                        dest='run_on_serial',
                        help='Run the installer over serial console.')
    parser.add_argument('--ascii', action='store_true',
                        dest='ascii',
                        help='Run the installer in ascii mode.')
    parser.add_argument('--unicode', action='store_false',
                        dest='ascii',
                        help='Run the installer in unicode mode.')
    parser.add_argument('--machine-config', metavar='CONFIG',
                        dest='machine_config',
                        help="Don't Probe. Use probe data file")
    parser.add_argument('--bootloader',
                        choices=['none', 'bios', 'prep', 'uefi'],
                        help='Override style of bootloader to use')
    parser.add_argument('--screens', action='append', dest='screens',
                        default=[])
    parser.add_argument('--script', metavar="SCRIPT", action='append',
                        dest='scripts', default=[],
                        help=('Execute SCRIPT in a namespace containing view '
                              'helpers and "ui"'))
    parser.add_argument('--click', metavar="PAT", action=ClickAction,
                        help='Synthesize a click on a button matching PAT')
    parser.add_argument('--answers')
    parser.add_argument('--autoinstall', action='store')
    with open('/proc/cmdline') as fp:
        cmdline = fp.read()
    parser.add_argument('--kernel-cmdline', action='store', default=cmdline)
    parser.add_argument('--source', default=[], action='append',
                        dest='sources', metavar='URL',
                        help='install from url instead of default.')
    parser.add_argument(
        '--snaps-from-examples', action='store_const', const=True,
        dest="snaps_from_examples",
        help=("Load snap details from examples/snaps instead of store. "
              "Default in dry-run mode.  "
              "See examples/snaps/README.md for more."))
    parser.add_argument(
        '--no-snaps-from-examples', action='store_const', const=False,
        dest="snaps_from_examples",
        help=("Load snap details from store instead of examples. "
              "Default in when not in dry-run mode.  "
              "See examples/snaps/README.md for more."))
    parser.add_argument(
        '--snap-section', action='store', default='server',
        help=("Show snaps from this section of the store in the snap "
              "list screen."))
    return parser.parse_args(argv)


LOGDIR = "/var/log/installer/"

AUTO_ANSWERS_FILE = "/subiquity_config/answers.yaml"


def main():
    # Prefer utils from $SNAP, over system-wide
    snap = os.environ.get('SNAP')
    if snap:
        os.environ['PATH'] = os.pathsep.join([
            os.path.join(snap, 'bin'),
            os.path.join(snap, 'usr', 'bin'),
            os.environ['PATH'],
        ])
    opts = parse_options(sys.argv[1:])
    global LOGDIR
    if opts.dry_run:
        LOGDIR = ".subiquity"
        if opts.snaps_from_examples is None:
            opts.snaps_from_examples = True
    logfiles = setup_logger(dir=LOGDIR)

    logger = logging.getLogger('subiquity')
    version = os.environ.get("SNAP_REVISION", "unknown")
    logger.info("Starting Subiquity revision {}".format(version))
    logger.info("Arguments passed: {}".format(sys.argv))

    if not opts.dry_run:
        ci_start = time.time()
        status_txt = run_command(["cloud-init", "status", "--wait"]).stdout
        logger.debug("waited %ss for cloud-init", time.time() - ci_start)
        if "status: done" in status_txt:
            logger.debug("loading cloud config")
            init = stages.Init()
            init.read_cfg()
            init.fetch(existing="trust")
            cloud = init.cloudify()
            if 'autoinstall' in cloud.cfg:
                atomic_helper.write_file(
                    '/autoinstall.yaml',
                    safeyaml.dumps(cloud.cfg['autoinstall']).encode('utf-8'),
                    mode=0o600)
                opts.autoinstall = '/autoinstall.yaml'
        else:
            logger.debug(
                "cloud-init status: %r, assumed disabled",
                status_txt)

    block_log_dir = os.path.join(LOGDIR, "block")
    os.makedirs(block_log_dir, exist_ok=True)
    handler = logging.FileHandler(os.path.join(block_log_dir, 'discover.log'))
    handler.setLevel('DEBUG')
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s:%(lineno)d %(message)s"))
    logging.getLogger('probert').addHandler(handler)
    handler.addFilter(lambda rec: rec.name != 'probert.network')
    logging.getLogger('curtin').addHandler(handler)
    logging.getLogger('block-discover').addHandler(handler)

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

    subiquity_interface = Subiquity(opts, block_log_dir)

    subiquity_interface.note_file_for_apport(
        "InstallerLog", logfiles['debug'])
    subiquity_interface.note_file_for_apport(
        "InstallerLogInfo", logfiles['info'])

    subiquity_interface.run()


if __name__ == '__main__':
    sys.exit(main())
