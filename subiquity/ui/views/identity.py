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
    LineBox,
    Pile,
    Text,
    WidgetWrap,
    )

from subiquitycore.ui.buttons import (
    cancel_btn,
    )
from subiquitycore.ui.interactive import (
    PasswordEditor,
    StringEditor,
    )
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
            self.bff.show_extra(("info_error", _("The characters : , and = are not permitted in this field")))
            return False
        else:
            return super().valid_char(ch)

class UsernameEditor(StringEditor, WantsToKnowFormField):
    def __init__(self):
        self.valid_char_pat = r'[-a-z0-9_]'
        self.error_invalid_char = _("The only characters permitted in this field are a-z, 0-9, _ and -")
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

_ssh_import_data = {
    None: {
        'caption': _("Import Username:"),
        'help': "",
        'valid_char': '.',
        'error_invalid_char': '',
        'regex': '.*',
        },
    'gh': {
        'caption': _("Github Username:"),
        'help': "Enter your Github username.",
        'valid_char': r'[a-zA-Z0-9\-]',
        'error_invalid_char': 'A Github username may only contain alphanumeric characters or hyphens.',
        },
    'lp': {
        'caption': _("Launchpad Username:"),
        'help': "Enter your Launchpad username.",
        'valid_char': r'[a-z0-9\+\.\-]',
        'error_invalid_char': 'A Launchpad username may only contain lower-case alphanumeric characters, hyphens, plus, or periods.',
        },
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
        help=_("You can import your SSH keys from Github or Launchpad."))
    import_username = UsernameField(_ssh_import_data[None]['caption'])

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

    # validation of the import username does not read from
    # ssh_import_id.value because it is sometimes done from the
    # 'select' signal of the import id selector, which is called
    # before the import id selector's value has actually changed. so
    # the signal handler stuffs the value here before doing
    # validation (yes, this is a hack).
    ssh_import_id_value = None
    def validate_import_username(self):
        if self.ssh_import_id_value is None:
            return
        username = self.import_username.value
        if len(username) == 0:
            return _("This field must not be blank.")
        if len(username) > SSH_IMPORT_MAXLEN:
            return _("SSH id too long, must be < ") + str(SSH_IMPORT_MAXLEN)
        if self.ssh_import_id_value == 'lp':
            lp_regex = r"^[a-z0-9][a-z0-9\+\.\-]+$"
            if not re.match(lp_regex, self.import_username.value):
                return _("""\
A Launchpad username must be at least two characters long and start with a letter or number. \
All letters must be lower-case. The characters +, - and . are also allowed after the first character.""")
        elif self.ssh_import_id_value == 'gh':
            if username.startswith('-') or username.endswith('-') or '--' in username or not re.match('^[a-zA-Z0-9\-]+$', username):
                return _("A Github username may only contain alphanumeric characters or single hyphens, and cannot begin or end with a hyphen.")


class FetchingSSHKeys(WidgetWrap):
    def __init__(self, parent):
        self.parent = parent
        spinner = Spinner(parent.controller.loop, style='dots')
        spinner.start()
        text = _("Fetching SSH keys...")
        button = cancel_btn(label=_("Cancel"), on_press=self.cancel)
        # | text |
        # 12    34
        self.width = len(text) + 4
        super().__init__(
            LineBox(
                Pile([
                    ('pack', Text(' ' + text)),
                    ('pack', spinner),
                    ])))
    def cancel(self):
        self.parent.remove_overlay()


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

        super().__init__(
            screen(
                self.form.as_rows(),
                button_pile([self.form.done_btn]),
                focus_buttons=False))
        self.form_rows = self._w[1]

    def _check_password(self, sender, new_text):
        password = self.form.password.value
        if not password.startswith(new_text):
            self.form.confirm_password.show_extra(("info_error", _("Passwords do not match")))
        else:
            self.form.confirm_password.show_extra('')

    def _select_ssh_import_id(self, sender, val):
        iu = self.form.import_username
        data = _ssh_import_data[val]
        iu.help = _(data['help'])
        iu.caption = _(data['caption'])
        iu.widget.valid_char_pat = data['valid_char']
        iu.widget.error_invalid_char = _(data['error_invalid_char'])
        iu.enabled = val is not None
        if val is not None:
            self.form_rows.body.focus += 2
        self.form.ssh_import_id_value = val
        if iu.value != "" or val is None:
            iu.validate()

    def done(self, result):
        result = {
            "hostname": self.form.hostname.value,
            "realname": self.form.realname.value,
            "username": self.form.username.value,
            "password": self.model.encrypt_password(self.form.password.value),
        }

        # if user specifed a value, allow user to validate fingerprint
        if self.form.ssh_import_id.value:
            fsk = FetchingSSHKeys(self)
            self.show_overlay(fsk, width=fsk.width, min_width=None)
            ssh_import_id = self.form.ssh_import_id.value + ":" + self.form.import_username.value
            self.controller.fetch_ssh_keys(result, ssh_import_id)
        else:
            log.debug("User input: {}".format(result))
            self.controller.done(result)
