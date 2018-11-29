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
    LineBox,
    Pile,
    Text,
    )

from subiquitycore.ui.buttons import (
    cancel_btn,
    ok_btn,
    other_btn,
    )
from subiquitycore.ui.container import (
    ListBox,
    WidgetWrap,
    )
from subiquitycore.ui.interactive import (
    PasswordEditor,
    StringEditor,
    )
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.form import (
    ChoiceField,
    Form,
    simple_field,
    WantsToKnowFormField,
    )
from subiquitycore.ui.utils import button_pile, screen
from subiquitycore.view import BaseView

from subiquity.ui.spinner import Spinner

log = logging.getLogger("subiquity.views.identity")

HOSTNAME_MAXLEN = 64
REALNAME_MAXLEN = 160
SSH_IMPORT_MAXLEN = 256 + 3  # account for lp: or gh:
USERNAME_MAXLEN = 32


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

    def __init__(self, reserved_usernames):
        self.reserved_usernames = reserved_usernames
        super().__init__()

    realname = RealnameField(_("Your name:"))
    hostname = UsernameField(
        _("Your server's name:"),
        help=_("The name it uses when it talks to other computers."))
    username = UsernameField(_("Pick a username:"))
    password = PasswordField(_("Choose a password:"))
    confirm_password = PasswordField(_("Confirm your password:"))

    def validate_realname(self):
        if len(self.realname.value) < 1:
            return _("Real name must not be empty.")
        if len(self.realname.value) > REALNAME_MAXLEN:
            return _("Realname too long, must be < ") + str(REALNAME_MAXLEN)

    def validate_hostname(self):
        if len(self.hostname.value) < 1:
            return _("Server name must not be empty")

        if len(self.hostname.value) > HOSTNAME_MAXLEN:
            return (_("Server name too long, must be < ") +
                    str(HOSTNAME_MAXLEN))

        if not re.match(r'[a-z_][a-z0-9_-]*', self.hostname.value):
            return _("Hostname must match NAME_REGEX, i.e. [a-z_][a-z0-9_-]*")

    def validate_username(self):
        username = self.username.value
        if len(username) < 1:
            return _("Username missing")

        if len(username) > USERNAME_MAXLEN:
            return _("Username too long, must be < ") + str(USERNAME_MAXLEN)

        if not re.match(r'[a-z_][a-z0-9_-]*', username):
            return _("Username must match NAME_REGEX, i.e. [a-z_][a-z0-9_-]*")

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


class IdentityView(BaseView):
    title = _("Profile setup")
    excerpt = _("Enter the username and password (or ssh identity) you "
                "will use to log in to the system.")

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.signal = controller.signal

        reserved_usernames_path = (
            os.path.join(os.environ.get("SNAP", "."), "reserved-usernames"))
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

        self.form = IdentityForm(reserved_usernames)

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form.confirm_password.widget, 'change',
                       self._check_password)

        super().__init__(
            screen(
                self.form.as_rows(),
                [self.form.done_btn],
                excerpt=_(self.excerpt),
                focus_buttons=False))

    def _check_password(self, sender, new_text):
        password = self.form.password.value
        if not password.startswith(new_text):
            self.form.confirm_password.show_extra(
                ("info_error", _("Passwords do not match")))
        else:
            self.form.confirm_password.show_extra('')

    def done(self, result):
        result = {
            "hostname": self.form.hostname.value,
            "realname": self.form.realname.value,
            "username": self.form.username.value,
            "password": self.model.encrypt_password(self.form.password.value),
        }
        self.controller.done(result)
