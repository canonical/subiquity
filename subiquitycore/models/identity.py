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
from subiquitycore.utils import crypt_password


log = logging.getLogger('subiquitycore.models.identity')


class LocalUser(object):
    def __init__(self, result):
        self._realname = result.get('realname')
        self._username = result.get('username')
        self._password = result.get('password')
        self._cpassword = result.get('confirm_password')
        self._ssh_import_id = None
        if 'ssh_import_id' in result:
            self._ssh_import_id = result.get('ssh_import_id')

    @property
    def realname(self):
        return self._realname

    @property
    def username(self):
        return self._username

    @property
    def password(self):
        return self._password

    @property
    def cpassword(self):
        return self._cpassword

    @property
    def ssh_import_id(self):
        return self._ssh_import_id

    def __repr__(self):
        return "%s <%s>" % (self._realname, self._username)


class IdentityModel(object):
    """ Model representing user identity
    """

    def __init__(self, opts):
        self.opts = opts
        self._user = None

    def add_user(self, result):
        if result:
            self._user = LocalUser(result)
        else:
            self._user = None

    @property
    def user(self):
        return self._user

    def encrypt_password(self, passinput):
        return crypt_password(passinput)

    def __repr__(self):
        return "<LocalUser: {}>".format(self.user)
