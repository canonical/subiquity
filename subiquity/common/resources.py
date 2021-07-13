# Copyright 2021 Canonical, Ltd.
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

# importlib-resources is a backport lib for importlib.resources
# With python 3.9 we can switch over to the built-in one.

import logging
import os

log = logging.getLogger('subiquity.common.resources')


def resource_path(relative_path):
    return os.path.join(os.environ.get("SNAP", "."), relative_path)
