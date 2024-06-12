# Copyright 2015 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import grp
import logging
import os

from subiquitycore.file_util import _DEF_PERMS, _DEF_GROUP


def setup_logger(dir, base='subiquity'):
    os.makedirs(dir, exist_ok=True)
    if os.getuid() == 0:
        os.chmod(dir, 0o750)
        os.chown(dir, -1, grp.getgrnam(_DEF_GROUP).gr_gid)

    logger = logging.getLogger("")
    logger.setLevel(logging.DEBUG)

    r = {}

    for level in 'info', 'debug':
        nopid_file = os.path.join(dir, "{}-{}.log".format(base, level))
        logfile = "{}.{}".format(nopid_file, os.getpid())
        handler = logging.FileHandler(logfile)
        os.chmod(logfile, _DEF_PERMS)
        if os.getuid() == 0:
            os.chown(logfile, -1, grp.getgrnam(_DEF_GROUP).gr_gid)
        # os.symlink cannot replace an existing file or symlink so create
        # it and then rename it over.
        tmplink = logfile + ".link"
        os.symlink(os.path.basename(logfile), tmplink)
        os.rename(tmplink, nopid_file)

        handler.setLevel(getattr(logging, level.upper()))
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s:%(lineno)d %(message)s"))

        logger.addHandler(handler)
        r[level] = logfile

    return r
