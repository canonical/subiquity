# Copyright 2018 Canonical, Ltd.
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
import platform
from urllib import parse

log = logging.getLogger('subiquitycore.models.mirror')

# correct default mirror for most arches
DEFAULT_MIRROR = 'http://ports.ubuntu.com/ubuntu-ports'
# apart from the two snowflakes
if platform.machine() in ['i686', 'x86_64']:
    DEFAULT_MIRROR = 'http://archive.ubuntu.com/ubuntu'


class MirrorModel(object):

    def __init__(self):
        self.mirror = DEFAULT_MIRROR

    def set_country(self, cc):
        parsed = parse.urlparse(DEFAULT_MIRROR)
        new = parsed._replace(netloc=cc + '.' + parsed.netloc)
        self.mirror = parse.urlunparse(new)

    def render(self):
        return {
             'apt': {
                 'primary': [{
                     'arches': ["default"],
                     'uri': self.mirror,
                     }],
                 }
            }
