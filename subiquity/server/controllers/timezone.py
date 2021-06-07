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
import subprocess

from subiquity.common.apidef import API
from subiquity.common.types import TimeZoneInfo
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.timezone')


def generate_possible_tzs():
    special_keys = ['', 'geoip']
    tzcmd = ['timedatectl', 'list-timezones']
    list_tz_out = subprocess.check_output(tzcmd, universal_newlines=True)
    real_tzs = list_tz_out.splitlines()
    return special_keys + real_tzs


class TimeZoneController(SubiquityController):

    endpoint = API.timezone

    possible = generate_possible_tzs()

    autoinstall_key = model_name = 'timezone'
    autoinstall_schema = {
        'type': 'string',
        'enum': possible
        }

    autoinstall_default = ''
    relevant_variants = ('desktop', )

    def load_autoinstall_data(self, data):
        self.deserialize(data)

    def make_autoinstall(self):
        return self.serialize()

    def serialize(self):
        return self.model.request

    def deserialize(self, data):
        if data is None:
            return
        if data not in self.possible:
            raise ValueError(f'Unrecognized time zone request "{data}"')
        self.model.set(data)
        # We could schedule a lookup here, but we already do so on
        # network-up, so that should be redundant.

    async def GET(self) -> TimeZoneInfo:
        if self.model.timezone:
            return TimeZoneInfo(self.model.timezone,
                                self.model.detect_with_geoip)

        # a bare call to GET() is equivalent to autoinstall
        # timezone: geoip
        self.deserialize('geoip')
        tz = self.app.geoip.timezone
        if tz:
            self.model.timezone = tz
        else:
            tz = 'UTC'
        return TimeZoneInfo(tz, self.model.detect_with_geoip)

    async def POST(self, data: str):
        log.debug('tz POST() %r', data)
        self.deserialize(data)
