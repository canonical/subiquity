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
import os
import sys
from logging.handlers import TimedRotatingFileHandler


def setup_logger(dir):
    LOGFILE = os.path.join(dir, "subiquity-debug.log")
    try:
        os.makedirs(dir, exist_ok=True)
        log = TimedRotatingFileHandler(LOGFILE,
                                       when='D',
                                       interval=1,
                                       backupCount=7)
    except PermissionError:
        err = ("Failed to open logfile: ") + LOGFILE
        sys.stderr.write(err + '\n')
        sys.exit(1)

    log.setLevel('DEBUG')
    log.setFormatter(
        logging.Formatter("%(asctime)s %(name)s:%(lineno)d %(message)s"))
    # log_filter = logging.Filter(name='subiquity')
    # log.addFilter(log_filter)

    logger = logging.getLogger('')
    logger.setLevel('DEBUG')
    logger.addHandler(log)
    return LOGFILE
