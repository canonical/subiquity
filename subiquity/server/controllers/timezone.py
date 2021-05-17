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
from subiquity.server.controller import SubiquityController
from subiquitycore.geoip import GeoIP

log = logging.getLogger('subiquity.server.controllers.timezone')


def generate_possible_tzs():
    special_keys = ['', 'geoip']
    tzcmd = ['timedatectl', 'list-timezones']
    list_tz_out = subprocess.check_output(tzcmd, text=True)
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

    autoinstall_default = ''  # FIXME handling of default status

    def load_autoinstall_data(self, data):
        self.deserialize(data)

    def make_autoinstall(self):
        return self.serialize()

    def serialize(self):
        return self.model.request

    def deserialize(self, data):
        if data not in self.possible:
            raise ValueError(f'Unrecognized time zone request "{data}"')
        self.model.set(data)
        if self.model.detect_with_geoip:
            sechedule_task(geoip_lookup)

    async def geoip_lookup(self):
        await self.app.geoip.lookup()
        self.model.timezone = self.app.geoip.time_zone

    async def GET(self) -> str:
        return self.serialize()

    async def POST(self, data: str):
        self.deserialize(data)

    async def geoip_lookup_POST(self) -> str:
        await self.geoip_lookup()
        return self.model.timezone
