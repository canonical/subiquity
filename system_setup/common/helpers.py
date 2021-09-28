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

import subprocess


def get_windows_locale():
    try:
        process = subprocess.Popen(["powershell.exe", "-NonInteractive",
                                    "-NoProfile", "-Command",
                                    "(Get-Culture).Name"],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        stdout, _ = process.communicate()
        if process.returncode:
            return None
        else:
            tmp_code = stdout.rstrip().decode("utf-8")
            tmp_code = tmp_code.replace("-", "_")
            return tmp_code
    except OSError:
        return None
