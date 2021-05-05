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

import logging
import sys

from subiquitycore.log import setup_logger
from subiquitycore import __version__ as VERSION

from console_conf.controllers.identity import write_login_details_standalone


def main():
    logger = setup_logger(dir='/var/log/console-conf')
    logger = logging.getLogger('console_conf')
    logger.info(
        "Starting console-conf-write-login-details v{}".format(VERSION))
    logger.info("Arguments passed: {}".format(sys.argv))
    return write_login_details_standalone()


if __name__ == '__main__':
    sys.exit(main())
