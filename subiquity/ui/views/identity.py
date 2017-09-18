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

from urwid import connect_signal

from subiquitycore.ui.interactive import (
    PasswordEditor,
    RealnameEditor,
    UsernameEditor,
    )
from subiquitycore.ui.form import (
    simple_field,
    Form,
    StringField,
    )
from subiquitycore.ui.container import ListBox
from subiquitycore.ui.utils import Padding
from subiquitycore.view import BaseView


log = logging.getLogger("subiquity.views.identity")

HOSTNAME_MAXLEN = 64
REALNAME_MAXLEN = 160
SSH_IMPORT_MAXLEN = 256 + 3  # account for lp: or gh:
USERNAME_MAXLEN = 32

RealnameField = simple_field(RealnameEditor)
UsernameField = simple_field(UsernameEditor)
PasswordField = simple_field(PasswordEditor)


class IdentityForm(Form):

    realname = RealnameField("Your name:")
    hostname = UsernameField(
        "Your server's name:",
        help="The name it uses when it talks to other computers.")
    username = UsernameField("Pick a username:")
    password = PasswordField("Choose a password:")
    confirm_password = PasswordField("Confirm your password:")
    ssh_import_id = StringField(
        "Import SSH identity:",
        help=("Input your SSH user id from Ubuntu SSO (sso:email), "
              "Launchpad (lp:username) or Github (gh:username)."))

    def validate_realname(self):
        if len(self.realname.value) < 1:
            return "Real name must not be empty."
        if len(self.realname.value) > REALNAME_MAXLEN:
            return "Realname too long, must be < " + str(REALNAME_MAXLEN)

    def validate_hostname(self):
        if len(self.hostname.value) < 1:
            return "Server name must not be empty"

        if len(self.hostname.value) > HOSTNAME_MAXLEN:
            return "Server name too long, must be < " + str(HOSTNAME_MAXLEN)

    def validate_username(self):
        if len(self.username.value) < 1:
            return "Username missing"

        if len(self.username.value) > USERNAME_MAXLEN:
            return "Username too long, must be < " + str(USERNAME_MAXLEN)

    def validate_password(self):
        # XXX we should not require a password if an ssh identity is provided
        # Form doesn't support form-wide validation yet though, oops.
        if len(self.password.value) < 1:
            return "Password must be set"

    def validate_confirm_password(self):
        if self.password.value != self.confirm_password.value:
            return "Passwords do not match"
        self.password.validate()

    def validate_ssh_import_id(self):
        if len(self.ssh_import_id.value) > SSH_IMPORT_MAXLEN:
            return "SSH id too long, must be < " + str(SSH_IMPORT_MAXLEN)


class IdentityView(BaseView):
    def __init__(self, model, controller, opts):
        self.model = model
        self.controller = controller
        self.signal = controller.signal
        self.opts = opts
        self.items = []

        self.form = IdentityForm()
        connect_signal(self.form, 'submit', self.done)

        self.ssh_import_confirmed = True

        self.right_button = self.form.done_btn

        body = [
            Padding.center_90(self.form.as_rows(self)),
        ]
        super().__init__(ListBox(body))

    def done(self, result):
        cpassword = self.model.encrypt_password(self.form.password.value)
        log.debug("*crypted* User input: {} {} {}".format(
            self.form.username.value, cpassword, cpassword))
        result = {
            "hostname": self.form.hostname.value,
            "realname": self.form.realname.value,
            "username": self.form.username.value,
            "password": cpassword,
            "confirm_password": cpassword,
        }

        # if user specifed a value, allow user to validate fingerprint
        if self.form.ssh_import_id.value:
            if self.ssh_import_confirmed is True:
                result.update({'ssh_import_id': self.form.ssh_import_id.value})
            else:
                self.emit_signal('identity:confirm-ssh-id',
                                 self.form.ssh_import_id.value)
                return

        log.debug("User input: {}".format(result))
        self.controller.create_user(result)
