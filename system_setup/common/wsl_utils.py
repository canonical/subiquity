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

import os
import logging
import subprocess

from subiquity.common.resources import resource_path

log = logging.getLogger("subiquity.system_setup.common.wsl_utils")


def is_reconfigure(is_dryrun):
    if is_dryrun and \
                 os.getenv("DRYRUN_RECONFIG") == "true":
        return True
    if_normaluser = False
    with open('/etc/passwd', 'r') as f:
        for line in f:
            # check every normal user except nobody (65534)
            if int(line.split(':')[2]) >= 1000 and \
               int(line.split(':')[2]) != 65534:
                if_normaluser = True
                break
    return not is_dryrun and if_normaluser


def get_windows_locale():
    windows_locale_failed_msg = (
        "Cannot determine Windows locale, fallback to default."
        " Reason of failure: "
    )

    try:
        process = subprocess.run(["powershell.exe", "-NonInteractive",
                                  "-NoProfile", "-Command",
                                  "(Get-Culture).Name"],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        if process.returncode:
            log.info(windows_locale_failed_msg +
                     process.stderr.decode("utf-8"))
            return None

        tmp_code = process.stdout.rstrip().decode("utf-8")
        tmp_code = tmp_code.replace("-", "_")
        return tmp_code
    except OSError as e:
        log.info(windows_locale_failed_msg + e.strerror)
        return None


def get_userandgroups():
    usergroups_path = resource_path('users-and-groups')
    build_usergroups_path = \
        os.path.realpath(__file__ + '/../../../users-and-groups')
    if os.path.isfile(build_usergroups_path):
        usergroups_path = build_usergroups_path

    user_groups = set()
    if os.path.exists(usergroups_path):
        with open(usergroups_path) as fp:
            for line in fp:
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                user_groups.add(line)
    oneline_usergroups = ",".join(user_groups)
    return oneline_usergroups
