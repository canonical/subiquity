# Copyright 2018 Canonical, Ltd.
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
    Text,
    )

from subiquitycore.view import (
    BaseView,
    )
from subiquitycore.ui.buttons import (
    cancel_btn,
    ok_btn,
    )
from subiquitycore.ui.container import (
    ListBox,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.form import (
    BooleanField,
    ChoiceField,
    Form,
)
from subiquitycore.ui.spinner import (
    Spinner,
    )
from subiquitycore.ui.stretchy import (
    Stretchy,
    )
from subiquitycore.ui.utils import (
    button_pile,
    screen,
    SomethingFailed,
    )

from subiquity.common.types import SSHData
from subiquity.ui.views.identity import (
    UsernameField,
    )


log = logging.getLogger('subiquity.ui.views.ssh')


SSH_IMPORT_MAXLEN = 256 + 3  # account for lp: or gh:

_ssh_import_data = {
    None: {
        'caption': _("Import Username:"),
        'help': "",
        'valid_char': '.',
        'error_invalid_char': '',
        'regex': '.*',
        },
    'gh': {
        'caption': _("GitHub Username:"),
        'help': _("Enter your GitHub username."),
        'valid_char': r'[a-zA-Z0-9\-]',
        'error_invalid_char': _('A GitHub username may only contain '
                                'alphanumeric characters or hyphens.'),
        },
    'lp': {
        'caption': _("Launchpad Username:"),
        'help': "Enter your Launchpad username.",
        'valid_char': r'[a-z0-9\+\.\-]',
        'error_invalid_char': _('A Launchpad username may only contain '
                                'lower-case alphanumeric characters, hyphens, '
                                'plus, or periods.'),
        },
    }


class SSHForm(Form):

    install_server = BooleanField(_("Install OpenSSH server"))

    ssh_import_id = ChoiceField(
        _("Import SSH identity:"),
        choices=[
            (_("No"), True, None),
            (_("from GitHub"), True, "gh"),
            (_("from Launchpad"), True, "lp"),
            ],
        help=_("You can import your SSH keys from GitHub or Launchpad."))

    import_username = UsernameField(_ssh_import_data[None]['caption'])

    pwauth = BooleanField(_("Allow password authentication over SSH"))

    cancel_label = _("Back")

    def __init__(self, initial):
        super().__init__(initial=initial)
        connect_signal(
            self.install_server.widget, 'change', self._toggle_server)
        self._toggle_server(None, self.install_server.value)

    def _toggle_server(self, sender, new_value):
        if new_value:
            self.ssh_import_id.enabled = True
            self.import_username.enabled = self.ssh_import_id.value is not None
            self.pwauth.enabled = self.ssh_import_id.value is not None
        else:
            self.ssh_import_id.enabled = False
            self.import_username.enabled = False
            self.pwauth.enabled = False

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
            lp_regex = r"^[a-z0-9][a-z0-9\+\.\-]*$"
            if not re.match(lp_regex, self.import_username.value):
                return _("A Launchpad username must start with a letter or "
                         "number. All letters must be lower-case. The "
                         "characters +, - and . are also allowed after "
                         "the first character.""")
        elif self.ssh_import_id_value == 'gh':
            if not re.match(r'^[a-zA-Z0-9\-]+$', username):
                return _("A GitHub username may only contain alphanumeric "
                         "characters or single hyphens, and cannot begin or "
                         "end with a hyphen.")


class FetchingSSHKeys(WidgetWrap):
    def __init__(self, parent):
        self.parent = parent
        spinner = Spinner(parent.controller.app.aio_loop, style='dots')
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
                    ('pack', button_pile([button])),
                    ])))

    def cancel(self, sender):
        self.parent.controller._fetch_cancel()
        self.parent.remove_overlay()


class ConfirmSSHKeys(Stretchy):
    def __init__(self, parent, ssh_data, key_material, fingerprints):
        self.parent = parent
        self.ssh_data = ssh_data
        self.key_material = key_material

        ok = ok_btn(label=_("Yes"), on_press=self.ok)
        cancel = cancel_btn(label=_("No"), on_press=self.cancel)

        if len(fingerprints) > 1:
            title = _("Confirm SSH keys")
            header = _("Keys with the following fingerprints were fetched. "
                       "Do you want to use them?")
        else:
            title = _("Confirm SSH key")
            header = _("A key with the following fingerprint was fetched. "
                       "Do you want to use it?")

        fingerprints = Pile([Text(fingerprint)
                             for fingerprint in fingerprints])

        super().__init__(
            title,
            [
                Text(header),
                Text(""),
                fingerprints,
                Text(""),
                button_pile([ok, cancel]),
            ], 2, 4)

    def cancel(self, sender):
        self.parent.remove_overlay()

    def ok(self, sender):
        self.ssh_data.authorized_keys = self.key_material.splitlines()
        self.parent.controller.done(self.ssh_data)


class SSHView(BaseView):

    title = _("SSH Setup")
    excerpt = _("You can choose to install the OpenSSH server package to "
                "enable secure remote access to your server.")

    def __init__(self, controller, ssh_data):
        self.controller = controller

        initial = {
            "install_server": ssh_data.install_server,
            "pwauth": ssh_data.allow_pw,
            }

        self.form = SSHForm(initial=initial)

        connect_signal(self.form.ssh_import_id.widget, 'select',
                       self._select_ssh_import_id)

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        self.form_rows = ListBox(self.form.as_rows())
        super().__init__(
            screen(
                self.form_rows,
                self.form.buttons,
                excerpt=_(self.excerpt),
                focus_buttons=False))

    def _select_ssh_import_id(self, sender, val):
        iu = self.form.import_username
        data = _ssh_import_data[val]
        iu.help = _(data['help'])
        iu.caption = _(data['caption'])
        iu.widget.valid_char_pat = data['valid_char']
        iu.widget.error_invalid_char = _(data['error_invalid_char'])
        iu.enabled = val is not None
        self.form.pwauth.enabled = val is not None
        # The logic here is a little tortured but the idea is that if
        # the users switches from not importing a key to importing
        # one, untick pwauth (but don't fiddle with the users choice
        # if just switching between import sources), and conversely if
        # the user is not importing a key then the box has to be
        # ticked (and disabled).
        if (val is None) != (self.form.ssh_import_id.value is None):
            self.form.pwauth.value = val is None
        if val is not None:
            self.form_rows.base_widget.body.focus += 2
        self.form.ssh_import_id_value = val
        if iu.value != "" or val is None:
            iu.validate()

    def done(self, sender):
        log.debug("User input: {}".format(self.form.as_data()))
        ssh_data = SSHData(
            install_server=self.form.install_server.value,
            allow_pw=self.form.pwauth.value)

        # if user specifed a value, allow user to validate fingerprint
        if self.form.ssh_import_id.value:
            ssh_import_id = self.form.ssh_import_id.value + ":" + \
              self.form.import_username.value
            fsk = FetchingSSHKeys(self)
            self.show_overlay(fsk, width=fsk.width, min_width=None)
            self.controller.fetch_ssh_keys(
                ssh_import_id=ssh_import_id, ssh_data=ssh_data)
        else:
            self.controller.done(ssh_data)

    def cancel(self, result=None):
        self.controller.cancel()

    def confirm_ssh_keys(self, ssh_data, ssh_import_id, ssh_key, fingerprints):
        self.remove_overlay()
        self.show_stretchy_overlay(
            ConfirmSSHKeys(self, ssh_data, ssh_key, fingerprints))

    def fetching_ssh_keys_failed(self, msg, stderr):
        self.remove_overlay()
        self.show_stretchy_overlay(SomethingFailed(self, msg, stderr))
