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

import logging
import os
from pathlib import Path

import owasp_logger

from subiquitycore.file_util import set_log_perms


def setup_logger(dir, base="subiquity"):
    logdir = Path(dir)

    logdir.mkdir(parents=True, exist_ok=True)
    # Create the log directory in such a way that users in the group may
    # write to this directory in the installation environment.
    log_dir_group = "adm"
    if os.getenv("SNAP_CONFINEMENT", "classic") == "strict":
        # strictly confined snaps are peculiar in the way that we will not be
        # able to chown the location as any other group than 'root', this if
        # fine though as the snap is already run as the root user and
        # effectively the logs location will be more closed
        log_dir_group = "root"
    set_log_perms(str(logdir), mode=0o770, group=log_dir_group)

    logger = logging.getLogger("")
    logger.setLevel(logging.DEBUG)

    r = {}

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s:%(lineno)d %(message)s"
    )

    def add_file_handle(
        symlink_name: str,
        *,
        level: str,
        crash_report_identifier: str | None,
        logger=logger,
        formatter=formatter,
    ):
        filename = f"{symlink_name}.{os.getpid()}"
        logfile = logdir / filename

        handler = logging.FileHandler(logfile)
        set_log_perms(str(logfile), group_write=False)

        # Now, let's update the symlink.
        # Path.symlink_to() cannot replace an existing file or symlink so
        # create it with a temporary name and rename it over.
        tmplink = logfile.with_name(f"{filename}.link")
        tmplink.symlink_to(logfile.name)
        tmplink.rename(logdir / symlink_name)

        if crash_report_identifier is not None:
            r[crash_report_identifier] = str(logfile)

        handler.setLevel(getattr(logging, level.upper()))
        handler.setFormatter(formatter)

        logger.addHandler(handler)

    add_file_handle(
        symlink_name=f"{base}-info.log",
        level="info",
        crash_report_identifier="info",
    )
    add_file_handle(
        symlink_name=f"{base}-debug.log",
        level="debug",
        crash_report_identifier="debug",
    )
    add_file_handle(
        symlink_name=f"{base}-security-events.log.ndjson",
        level="info",
        crash_report_identifier=None,
        logger=logging.getLogger("owasp"),
        # The OWASPLogger methods ensure the message passed to logging.log is a
        # one-line JSON record, including all necessary info. To make sure we
        # have a valid NDJSON file, let's not involve any further formatting.
        formatter=None,
    )

    owasp_log = get_owasp_logger()
    owasp_log.appid = base

    return r


def get_owasp_logger():
    """Return a shared instance of OWASPLogger"""
    global _owasp_logger

    _owasp_logger = None

    if _owasp_logger is None:
        # We set the appid to a temporary value. One should use setup_logger to
        # set it correctly.
        _owasp_logger = owasp_logger.OWASPLogger(
            appid="subiquity", logger=logging.getLogger("owasp")
        )
    return _owasp_logger
