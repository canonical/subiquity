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

import logging

log = logging.getLogger('subiquity.models.timezone')


class TimeZoneModel(object):
    """ Model representing timezone"""

    timezone = ''

    def __init__(self):
        self._request = None
        self._time_zone = ''

    def set(self, value):
        self._request = value
        if value != 'geoip' and value != '':
            self._time_zone = value
        else:
            self._time_zone = ''

    @property
    def detect_with_geoip(self):
        return self._request == 'geoip'

    @property
    def should_set_tz(self):
        return bool(self._time_zone)

    @property
    def timezone(self):
        return self._time_zone

    @timezone.setter
    def timezone(self, tz):
        self._time_zone = tz

    @property
    def request(self):
        return self._request

    def __repr__(self):
        return "<TimeZone: detect {} should_set {} timezone {}>".format(
            self.detect_with_geoip, self.should_set_tz, self._time_zone)
