# Copyright 2015 Canonical, Ltd.
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
from subiquity.model import ModelPolicy


log = logging.getLogger('subiquity.login')


class LoginModel(ModelPolicy):
    """ Model representing Final login screen
    """
    prev_signal = 'menu:identity:main'

    signals = [
        ("Login view",
         'menu:login:main',
         'login')
    ]

    configured_logins = [
        'local',
        'ssh'
    ]

    def get_signals(self):
        return self.signals

    def get_menu(self):
        return self.configured_logins

    def get_signal_by_name(self, selection):
        for x, y, z in self.get_menu():
            if x == selection:
                return y

    def __repr__(self):
        return "<Configured: {}>".format(self.configured_logins)
