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
import re

from urwid import (
    connect_signal,
    Text,
    WidgetWrap,
    )

from subiquitycore.ui.interactive import (
    PasswordEditor,
    StringEditor,
    )
from subiquitycore.ui.container import (
    ListBox,
    Pile,
    )
from subiquitycore.ui.form import (
    ChoiceField,
    Form,
    simple_field,
    WantsToKnowFormField,
    )
from subiquitycore.ui.selector import Selector
from subiquitycore.ui.utils import button_pile, Padding
from subiquitycore.view import BaseView


log = logging.getLogger("subiquity.views.identity")

HOSTNAME_MAXLEN = 64
REALNAME_MAXLEN = 160
SSH_IMPORT_MAXLEN = 256 + 3  # account for lp: or gh:
USERNAME_MAXLEN = 32

class RealnameEditor(StringEditor, WantsToKnowFormField):
    def valid_char(self, ch):
        if len(ch) == 1 and ch in ':,=':
            self.bff.in_error = True
            self.bff.show_extra(("info_error", "The characters : , and = are not permitted in this field"))
            return False
        else:
            return super().valid_char(ch)

class UsernameEditor(StringEditor, WantsToKnowFormField):
    def valid_char(self, ch):
        if len(ch) == 1 and not re.match('[a-z0-9_-]', ch):
            self.bff.in_error = True
            self.bff.show_extra(("info_error", "The only characters permitted in this field are a-z, 0-9, _ and -"))
            return False
        else:
            return super().valid_char(ch)

RealnameField = simple_field(RealnameEditor)
UsernameField = simple_field(UsernameEditor)
PasswordField = simple_field(PasswordEditor)

_ssh_import_helps = {
    None: "",
    "gh": _("Enter your github username."),
    "lp": _("Enter your Launchpad username."),
    }
_ssh_import_captions = {
    None: _("Import Username:"),
    "gh": _("Github username:"),
    "lp": _("Launchpad username:"),
    }

class IdentityForm(Form):

    realname = RealnameField(_("Your name:"))
    hostname = UsernameField(
        _("Your server's name:"),
        help=_("The name it uses when it talks to other computers."))
    username = UsernameField(_("Pick a username:"))
    password = PasswordField(_("Choose a password:"))
    confirm_password = PasswordField(_("Confirm your password:"))
    ssh_import_id = ChoiceField(
        _("Import SSH identity:"),
        choices=[
            (_("No"), True, None),
            (_("from Github"), True, "gh"),
            (_("from Launchpad"), True, "lp"),
            #(_("from Ubuntu One account"), True, "sso"),
            ],
        help=_("You can import your SSH keys from Github, Launchpad or Ubuntu One."))
    import_username = UsernameField(_ssh_import_captions[None])

    def validate_realname(self):
        if len(self.realname.value) < 1:
            return _("Real name must not be empty.")
        if len(self.realname.value) > REALNAME_MAXLEN:
            return _("Realname too long, must be < ") + str(REALNAME_MAXLEN)

    def validate_hostname(self):
        if len(self.hostname.value) < 1:
            return _("Server name must not be empty")

        if len(self.hostname.value) > HOSTNAME_MAXLEN:
            return _("Server name too long, must be < ") + str(HOSTNAME_MAXLEN)

        if not re.match(r'[a-z_][a-z0-9_-]*', self.hostname.value):
            return _("Hostname must match NAME_REGEX, i.e. [a-z_][a-z0-9_-]*")

    def validate_username(self):
        if len(self.username.value) < 1:
            return _("Username missing")

        if len(self.username.value) > USERNAME_MAXLEN:
            return _("Username too long, must be < ") + str(USERNAME_MAXLEN)

        if not re.match(r'[a-z_][a-z0-9_-]*', self.username.value):
            return _("Username must match NAME_REGEX, i.e. [a-z_][a-z0-9_-]*")

    def validate_password(self):
        if len(self.password.value) < 1:
            return _("Password must be set")

    def validate_confirm_password(self):
        if self.password.value != self.confirm_password.value:
            return _("Passwords do not match")
        self.password.validate()

    def validate_import_username(self):
        if self.ssh_import_id.value is None:
            return
        if len(self.import_username.value) == 0:
            return _("This field must not be blank.")
        if len(self.import_username.value) > SSH_IMPORT_MAXLEN:
            return _("SSH id too long, must be < ") + str(SSH_IMPORT_MAXLEN)


class IdentityView(BaseView):
    def __init__(self, model, controller, opts):
        self.model = model
        self.controller = controller
        self.signal = controller.signal
        self.opts = opts
        self.items = []

        self.form = IdentityForm()
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form.confirm_password.widget, 'change', self._check_password)
        connect_signal(self.form.ssh_import_id.widget, 'select', self._select_ssh_import_id)
        self.form.import_username.enabled = False

        self.ssh_import_confirmed = True

        self.form_rows = self.form.as_rows(self)

        body = Pile([
            ('pack', Text("")),
            Padding.center_90(ListBox([self.form_rows])),
            ('pack', Pile([
                ('pack', Text("")),
                button_pile([self.form.done_btn]),
                ('pack', Text("")),
                ], focus_item=1)),
            ])
        super().__init__(body)

    def _check_password(self, sender, new_text):
        password = self.form.password.value
        if not password.startswith(new_text):
            self.form.confirm_password.show_extra(("info_error", "Passwords do not match"))
        else:
            self.form.confirm_password.show_extra('')

    def _select_ssh_import_id(self, sender, val):
        iu = self.form.import_username
        iu.help = _ssh_import_helps[val]
        iu.caption = _ssh_import_captions[val]
        iu.enabled = val is not None
        if val is not None:
            self.form_rows.focus_position += 1

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
                ssh_import_id = self.form.ssh_import_id.value + ":" + self.form.import_username.value
                result.update({'ssh_import_id': ssh_import_id})
            else:
                self.emit_signal('identity:confirm-ssh-id',
                                 self.form.ssh_import_id.value)
                return

        log.debug("User input: {}".format(result))
        self.controller.create_user(result)
