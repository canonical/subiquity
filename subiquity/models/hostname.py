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


log = logging.getLogger('subiquity.models.hostname')


class HostnameModel(ModelPolicy):
    """ Model representing system hostname
    """
    prev_signal = ('Back to filesystem view',
                   'filesystem:show',
                   'filesystem')

    signals = [
        ("Hostname View",
         'hostname:show',
         'hostname')
    ]

    hostname_menu = []

    def get_signals(self):
        return self.signals

    def get_menu(self):
        return self.hostname_menu

    def get_signal_by_name(self, selection):
        for x, y, z in self.get_menu():
            if x == selection:
                return y

    def __repr__(self):
        return "<Hostname: {}>".format(self.hostname)
