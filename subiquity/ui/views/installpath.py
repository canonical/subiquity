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

""" Install Path

Provides high level options for Ubuntu install

"""
import binascii
import logging
import re

import lsb_release

from urwid import connect_signal

from subiquitycore.ui.buttons import back_btn, forward_btn
from subiquitycore.ui.utils import screen
from subiquitycore.view import BaseView
from subiquitycore.ui.interactive import (
    PasswordEditor,
    )
from subiquity.ui.views.identity import (
    UsernameField,
    PasswordField,
    USERNAME_MAXLEN,
    )
from subiquitycore.ui.form import (
    Form,
    simple_field,
    URLField,
    WantsToKnowFormField,
)


log = logging.getLogger('subiquity.installpath')


class InstallpathView(BaseView):
    title = "Ubuntu {}"

    excerpt = _("Welcome to Ubuntu! The world's favourite platform "
                "for clouds, clusters, and amazing internet things. "
                "This is the installer for Ubuntu on servers and "
                "internet devices.")
    footer = _("Use UP, DOWN arrow keys, and ENTER, to "
               "navigate options")

    def __init__(self, model, controller):
        self.title = self.title.format(lsb_release.get_distro_information()['RELEASE'])
        self.model = model
        self.controller = controller
        self.items = []
        back = back_btn(_("Back"), on_press=self.cancel)
        super().__init__(screen(
            self._build_choices(), [back],
            focus_buttons=False, excerpt=_(self.excerpt)))

    def _build_choices(self):
        choices = []
        for label, path in self.model.paths:
            log.debug("Building inputs: {}".format(path))
            choices.append(
                forward_btn(
                    label=label, on_press=self.confirm, user_arg=path))
        return choices

    def confirm(self, sender, path):
        self.controller.choose_path(path)

    def cancel(self, button=None):
        self.controller.cancel()


class RegionForm(Form):

    username = UsernameField(
        _("Pick a username for the admin account:"),
        help=_("Enter the administrative username."))
    password = PasswordField(
        _("Choose a password:"),
        help=_("Please enter the password for this account."))

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


# Copied from MAAS:
def to_bin(u):
    """Convert ASCII-only unicode string to hex encoding."""
    assert isinstance(u, str), "%r is not a unicode string" % (u,)
    # Strip ASCII whitespace from u before converting.
    return binascii.a2b_hex(u.encode("ascii").strip())


class RackSecretEditor(PasswordEditor, WantsToKnowFormField):
    def __init__(self):
        self.valid_char_pat = r'[a-fA-F0-9]'
        self.error_invalid_char = _("The secret can only contain hexadecimal "
                                    "characters, i.e. 0-9, a-f, A-F.")
        super().__init__()

    def valid_char(self, ch):
        if len(ch) == 1 and not re.match(self.valid_char_pat, ch):
            self.bff.in_error = True
            self.bff.show_extra(("info_error", self.error_invalid_char))
            return False
        else:
            return super().valid_char(ch)

RackSecretField = simple_field(RackSecretEditor)


class RackForm(Form):

    url = URLField(
        _("Ubuntu MAAS Region API address:"),
        help=_("e.g. \"http://192.168.1.1:5240/MAAS\". "
               "localhost or 127.0.0.1 are not useful values here."))

    secret = RackSecretField(
        _("MAAS shared secret:"),
        help=_("The secret can be found in /var/lib/maas/secret "
               "on the region controller. "))

    def validate_url(self):
        if len(self.url.value) < 1:
            return _("API address must be set")

    def validate_secret(self):
        if len(self.secret.value) < 1:
            return _("Secret must be set")
        try:
            to_bin(self.secret.value)
        except binascii.Error as error:
            return _("Secret could not be decoded: %s") % (error,)


class MAASView(BaseView):

    def __init__(self, model, controller, title, excerpt):
        self.model = model
        self.controller = controller
        self.signal = controller.signal
        self.items = []
        self.title = title

        if self.model.path == "maas_region":
            self.form = RegionForm()
        elif self.model.path == "maas_rack":
            self.form = RackForm()
        else:
            raise ValueError("invalid MAAS form %s" % self.model.path)

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        super().__init__(self.form.as_screen(focus_buttons=False, excerpt=excerpt))

    def done(self, result):
        log.debug("User input: {}".format(result.as_data()))
        self.controller.setup_maas(result.as_data())

    def cancel(self, result=None):
        self.controller.default()
