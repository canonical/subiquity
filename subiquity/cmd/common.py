# Copyright 2020 Canonical, Ltd.
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

import locale
import os

LOGDIR = "/var/log/installer/"


def setup_environment():
    # Python 3.7+ does more or less this by default, but we need to
    # work with the Python 3.6 in bionic.
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        locale.setlocale(locale.LC_CTYPE, "C.UTF-8")

    # Prefer utils from $SNAP, over system-wide
    snap = os.environ.get('SNAP')
    if snap:
        os.environ['PATH'] = os.pathsep.join([
            os.path.join(snap, 'bin'),
            os.path.join(snap, 'usr', 'bin'),
            os.environ['PATH'],
        ])
        os.environ["APPORT_DATA_DIR"] = os.path.join(snap, 'share/apport')
