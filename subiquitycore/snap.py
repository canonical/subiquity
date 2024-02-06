# Copyright 2024 Canonical, Ltd.
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


# Returns true if the current execution environment is inside a snap.
def is_snap():
    return os.getenv("SNAP_CONFINEMENT") is not None


# Returns true if the current execution environment is inside a strictly
# confined snap.
def is_snap_strictly_confined():
    return os.getenv("SNAP_CONFINEMENT", "classic") == "strict"


# Returns the snap name if the current execution context is inside a snap,
# otherwise None.
def snap_name():
    return os.getenv("SNAP_INSTANCE_NAME")
