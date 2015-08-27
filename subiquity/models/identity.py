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


log = logging.getLogger('subiquity.models.identity')


class IdentityModel(ModelPolicy):
    """ Model representing user identity
    """
    # TODO: Set to installer progress output view
    prev_signal = ('Back to filesystem view',
                   'filesystem:show',
                   'filesystem')

    signals = [
        ("Identity view",
         'identity:show',
         'identity')
    ]

    identity_menu = [
        ("Username",
         "identity:username",
         "validate_username"),
        ("Password",
         "identity:password",
         "validate_password"),
        ("Confirm Password",
         "identity:confirm-password",
         "validate_confirm_password")
    ]

    def get_signals(self):
        return self.signals

    def get_menu(self):
        return self.identity_menu

    def get_signal_by_name(self, selection):
        for x, y, z in self.get_menu():
            if x == selection:
                return y

    def encrypt_password(self):
        # TODO: implement
        pass

    def __repr__(self):
        return "<Username: {}>".format(self.username)
