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
from logging.handlers import TimedRotatingFileHandler


def setup_logger(name=__name__):
    LOGDIR = "logs"
    LOGFILE = os.path.join(LOGDIR, "debug.log")
    if not os.path.isdir(LOGDIR):
        os.makedirs(LOGDIR)
    log = TimedRotatingFileHandler(LOGFILE,
                                   when='D',
                                   interval=1,
                                   backupCount=7)
    log.setLevel('DEBUG')
    log.setFormatter(logging.Formatter(
        "%(asctime)s "
        "%(name)s:%(lineno)d %(message)s",
        datefmt='%m/%d %H:%M'))
    log_filter = logging.Filter(name='probert')
    log.addFilter(log_filter)

    logger = logging.getLogger('')
    logger.setLevel('DEBUG')
    logger.addHandler(log)
    return logger
