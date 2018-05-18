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

import attr

from subiquitycore.utils import crypt_password


log = logging.getLogger('subiquitycore.models.identity')


@attr.s
class User(object):
    realname = attr.ib()
    username = attr.ib()
    password = attr.ib()
    ssh_keys = attr.ib(default=attr.Factory(list))


class IdentityModel(object):
    """ Model representing user identity
    """

    def __init__(self):
        self._user = None
        self._hostname = None

    def add_user(self, result):
        result = result.copy()
        self._hostname = result.pop('hostname')
        self._user = User(**result)

    @property
    def hostname(self):
        return self._hostname

    @property
    def user(self):
        return self._user

    def encrypt_password(self, passinput):
        return crypt_password(passinput)

    def __repr__(self):
        return "<LocalUser: {} {}>".format(self.user, self.hostname)
