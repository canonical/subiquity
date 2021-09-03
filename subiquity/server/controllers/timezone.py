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
from shutil import which
import os

log = logging.getLogger('subiquity.server.controllers.timezone')


def active_timedatectl():
    return which('timedatectl') and os.path.exists('/run/systemd/system')


def generate_possible_tzs():
    special_keys = ['', 'geoip']
    if not active_timedatectl():
        return special_keys
    tzcmd = ['timedatectl', 'list-timezones']
    list_tz_out = subprocess.check_output(tzcmd, universal_newlines=True)
    real_tzs = list_tz_out.splitlines()
    return special_keys + real_tzs


def timedatectl_settz(app, tz):
    tzcmd = ['timedatectl', 'set-timezone', tz]
    if app.opts.dry_run:
        tzcmd = ['sleep', str(1/app.scale_factor)]

    try:
        subprocess.run(tzcmd, universal_newlines=True)
    except subprocess.CalledProcessError as cpe:
        log.error('Failed to set live system timezone: %r', cpe)


def timedatectl_gettz():
    # timedatectl show would be easier, but isn't on bionic
    tzcmd = ['timedatectl', 'status']
    env = {'LC_ALL': 'C'}
    # ...
    #    Time zone: America/Denver (MDT, -0600)
    # ...
    try:
        out = subprocess.check_output(tzcmd, env=env, universal_newlines=True)
        for line in out.splitlines():
            chunks = line.split(':')
            label = chunks[0].strip()
            if label != 'Time zone':
                continue
            chunks = chunks[1].split(' ')
            return chunks[1]
    except subprocess.CalledProcessError as cpe:
        log.error('Failed to get live system timezone: %r', cpe)
    except IndexError:
        log.error('Failed to acquire system time zone')
    log.debug('Failed to find Time zone in timedatectl output')
    return 'Etc/UTC'


class TimeZoneController(SubiquityController):

    endpoint = API.timezone

    possible = generate_possible_tzs()

    autoinstall_key = model_name = 'timezone'
    autoinstall_schema = {
        'type': 'string',
        'enum': possible
        }

    autoinstall_default = ''

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
        if self.model.detect_with_geoip and self.app.geoip.timezone:
            self.model.timezone = self.app.geoip.timezone
            self.model.got_from_geoip = True
        else:
            self.model.got_from_geoip = False
        self.set_system_timezone()

    def set_system_timezone(self):
        if self.model.should_set_tz:
            timedatectl_settz(self.app, self.model.timezone)

    async def GET(self) -> TimeZoneInfo:
        # if someone POSTed before, return that
        if self.model.timezone:
            return TimeZoneInfo(self.model.timezone,
                                self.model.got_from_geoip)

        # GET requests geoip results
        if self.app.geoip.timezone:
            return TimeZoneInfo(self.app.geoip.timezone, True)

        # geoip wasn't ready for some reason, so ask the system
        return TimeZoneInfo(timedatectl_gettz(), False)

    async def POST(self, tz: str):
        self.deserialize(tz)
        self.configured()
