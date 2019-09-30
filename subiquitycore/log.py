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


def setup_logger(dir):
    os.makedirs(dir, exist_ok=True)
    LOGFILE = os.path.join(dir, "subiquity-debug.log.{}".format(os.getpid()))
    handler = logging.FileHandler(LOGFILE)

    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s:%(lineno)d %(message)s"))

    logger = logging.getLogger("")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return LOGFILE
