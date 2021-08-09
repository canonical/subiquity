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

import os
import re
from subiquity.common.resources import resource_path
from urwid import (
    connect_signal,
    )


from subiquity.common.types import IdentityData
from subiquity.ui.views.identity import IdentityForm, IdentityView, PasswordField, RealnameField, UsernameField, setup_password_validation
from subiquitycore.ui.form import Form
from subiquitycore.ui.utils import screen
from subiquitycore.utils import crypt_password
from subiquitycore.view import BaseView

HOSTNAME_MAXLEN = 64
HOSTNAME_REGEX = r'[a-z0-9_][a-z0-9_-]*'
REALNAME_MAXLEN = 160
SSH_IMPORT_MAXLEN = 256 + 3  # account for lp: or gh:
USERNAME_MAXLEN = 32
USERNAME_REGEX = r'[a-z_][a-z0-9_-]*'

class WSLIdentityForm(Form):

    def __init__(self, reserved_usernames, initial):
        self.reserved_usernames = reserved_usernames
        super().__init__(initial=initial)

    realname = RealnameField(_("Your name:"))
    username = UsernameField(_("Pick a username:"), help=_("The username does not need to match your Windows username"))
    password = PasswordField(_("Choose a password:"))
    confirm_password = PasswordField(_("Confirm your password:"))

    def validate_realname(self):
        if len(self.realname.value) > REALNAME_MAXLEN:
            return _(
                "Name too long, must be less than {limit}"
                ).format(limit=REALNAME_MAXLEN)

    def validate_hostname(self):
        if len(self.hostname.value) < 1:
            return _("Server name must not be empty")

        if len(self.hostname.value) > HOSTNAME_MAXLEN:
            return _(
                "Server name too long, must be less than {limit}"
                ).format(limit=HOSTNAME_MAXLEN)

        if not re.match(HOSTNAME_REGEX, self.hostname.value):
            return _(
                "Hostname must match HOSTNAME_REGEX: " + HOSTNAME_REGEX)

    def validate_username(self):
        username = self.username.value
        if len(username) < 1:
            return _("Username missing")

        if len(username) > USERNAME_MAXLEN:
            return _(
                "Username too long, must be less than {limit}"
                ).format(limit=USERNAME_MAXLEN)

        if not re.match(r'[a-z_][a-z0-9_-]*', username):
            return _(
                "Username must match USERNAME_REGEX: " + USERNAME_REGEX)

        if username in self.reserved_usernames:
            return _(
                'The username "{username}" is reserved for use by the system.'
                ).format(username=username)

    def validate_password(self):
        if len(self.password.value) < 1:
            return _("Password must be set")

    def validate_confirm_password(self):
        if self.password.value != self.confirm_password.value:
            return _("Passwords do not match")


class WSLIdentityView(BaseView):
    title = IdentityView.title
    excerpt = _("Please create a default UNIX user account. "
                "For more information visit: https://aka.ms/wslusers")

    def __init__(self, controller, identity_data):
        self.controller = controller

        reserved_usernames_path = resource_path('reserved-usernames')
        reserved_usernames = set()
        if os.path.exists(reserved_usernames_path):
            with open(reserved_usernames_path) as fp:
                for line in fp:
                    line = line.strip()
                    if line.startswith('#') or not line:
                        continue
                    reserved_usernames.add(line)
        else:
            reserved_usernames.add('root')

        initial = {
            'realname': identity_data.realname,
            'username': identity_data.username,
            }

        self.form = WSLIdentityForm(reserved_usernames, initial)

        connect_signal(self.form, 'submit', self.done)
        setup_password_validation(self.form, _("passwords"))

        super().__init__(
            screen(
                self.form.as_rows(),
                [self.form.done_btn],
                excerpt=_(self.excerpt),
                focus_buttons=False))

    def done(self, result):
        self.controller.done(IdentityData(
            realname=self.form.realname.value,
            username=self.form.username.value,
            crypted_password=crypt_password(self.form.password.value),
            ))
