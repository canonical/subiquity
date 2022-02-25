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
import os
import re

from urwid import (
    connect_signal,
    )

from subiquitycore.ui.interactive import (
    PasswordEditor,
    StringEditor,
    )
from subiquitycore.ui.form import (
    Form,
    simple_field,
    WantsToKnowFormField,
    )
from subiquitycore.ui.utils import screen
from subiquitycore.utils import crypt_password
from subiquitycore.view import BaseView

from subiquity.common.resources import resource_path
from subiquity.common.types import IdentityData


log = logging.getLogger("subiquity.ui.views.identity")

HOSTNAME_MAXLEN = 64
HOSTNAME_REGEX = r'[a-z0-9_][a-z0-9_-]*'
REALNAME_MAXLEN = 160
SSH_IMPORT_MAXLEN = 256 + 3  # account for lp: or gh:
USERNAME_MAXLEN = 32
USERNAME_REGEX = r'[a-z_][a-z0-9_-]*'


class RealnameEditor(StringEditor, WantsToKnowFormField):
    def valid_char(self, ch):
        if len(ch) == 1 and ch in ':,=':
            self.bff.in_error = True
            self.bff.show_extra(("info_error",
                                 _("The characters : , and = are not permitted"
                                   " in this field")))
            return False
        else:
            return super().valid_char(ch)


class UsernameEditor(StringEditor, WantsToKnowFormField):
    def __init__(self):
        self.valid_char_pat = r'[-a-z0-9_]'
        self.error_invalid_char = _("The only characters permitted in this "
                                    "field are a-z, 0-9, _ and -")
        super().__init__()

    def valid_char(self, ch):
        if len(ch) == 1 and not re.match(self.valid_char_pat, ch):
            self.bff.in_error = True
            self.bff.show_extra(("info_error", self.error_invalid_char))
            return False
        else:
            return super().valid_char(ch)


RealnameField = simple_field(RealnameEditor)
UsernameField = simple_field(UsernameEditor)
PasswordField = simple_field(PasswordEditor)


class IdentityForm(Form):

    def __init__(self, reserved_usernames, initial):
        self.reserved_usernames = reserved_usernames
        super().__init__(initial=initial)

    realname = RealnameField(_("Your name:"))
    hostname = UsernameField(
        _("Your server's name:"),
        help=_("The name it uses when it talks to other computers."))
    username = UsernameField(_("Pick a username:"))
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


def setup_password_validation(form, desc):
    def _check_password(sender, new_text):
        password = form.password.value
        if not password.startswith(new_text):
            form.confirm_password.show_extra(
                # desc is "passwords" or "passphrases"
                ("info_error", _("{desc} do not match").format(desc=desc)))
        else:
            form.confirm_password.show_extra('')
    connect_signal(
        form.confirm_password.widget, 'change', _check_password)


class IdentityView(BaseView):
    title = _("Profile setup")
    excerpt = _("Enter the username and password you will use to log in to "
                "the system. You can configure SSH access on the next screen "
                "but a password is still needed for sudo.")

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
            'hostname': identity_data.hostname,
            }

        self.form = IdentityForm(reserved_usernames, initial)

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
            hostname=self.form.hostname.value,
            realname=self.form.realname.value,
            username=self.form.username.value,
            crypted_password=crypt_password(self.form.password.value),
            ))
