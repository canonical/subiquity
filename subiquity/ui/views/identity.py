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

from urwid import connect_signal

from subiquity.common.resources import resource_path
from subiquity.common.types import IdentityData, UsernameValidation
from subiquitycore.async_helpers import schedule_task
from subiquitycore.ui.form import Form, WantsToKnowFormField, simple_field
from subiquitycore.ui.interactive import PasswordEditor, StringEditor
from subiquitycore.ui.utils import screen
from subiquitycore.utils import crypt_password
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.ui.views.identity")

HOSTNAME_MAXLEN = 64
HOSTNAME_REGEX = r"[a-z0-9_][a-z0-9_-]*"
REALNAME_MAXLEN = 160
SSH_IMPORT_MAXLEN = 256 + 3  # account for lp: or gh:
USERNAME_MAXLEN = 32
USERNAME_REGEX = r"[a-z_][a-z0-9_-]*"


class RealnameEditor(StringEditor, WantsToKnowFormField):
    def valid_char(self, ch):
        if len(ch) == 1 and ch in ":,=":
            self.bff.in_error = True
            self.bff.show_extra(
                (
                    "info_error",
                    _("The characters : , and = are not permitted in this field"),
                )
            )
            return False
        else:
            return super().valid_char(ch)


class _AsyncValidatedMixin:
    """Provides Editor widgets with async validation capabilities"""

    def __init__(self):
        self.validation_task = None
        self.initial = None
        self.validation_result = None
        self._validate_async_inner = None
        connect_signal(self, "change", self._reset_validation)

    def set_initial_state(self, initial):
        self.initial = initial
        self.validation_result = initial

    def _reset_validation(self, _, __):
        self.validation_result = self.initial

    def set_validation_call(self, async_call):
        self._validate_async_inner = async_call

    def lost_focus(self):
        if self.validation_task is not None:
            self.validation_task.cancel()

        self.validation_task = schedule_task(self._validate_async(self.value))

    async def _validate_async(self, value):
        # Retrigger field validation because it's not guaranteed that the async
        # call result will be available when the form fields are validated.
        if self._validate_async_inner is not None:
            self.validation_result = await self._validate_async_inner(value)
            self.bff.validate()


class UsernameEditor(StringEditor, _AsyncValidatedMixin, WantsToKnowFormField):
    def __init__(self):
        self.valid_char_pat = r"[-a-z0-9_]"
        self.error_invalid_char = _(
            "The only characters permitted in this field are a-z, 0-9, _ and -"
        )
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
    def __init__(self, controller, initial):
        self.controller = controller
        super().__init__(initial=initial)
        widget = self.username.widget
        widget.set_initial_state(UsernameValidation.OK)
        widget.set_validation_call(self.controller.validate_username)

    realname = RealnameField(_("Your name:"))
    hostname = UsernameField(
        _("Your server's name:"),
        help=_("The name it uses when it talks to other computers."),
    )
    username = UsernameField(_("Pick a username:"))
    password = PasswordField(_("Choose a password:"))
    confirm_password = PasswordField(_("Confirm your password:"))

    def validate_realname(self):
        if len(self.realname.value) > REALNAME_MAXLEN:
            return _("Name too long, must be less than {limit}").format(
                limit=REALNAME_MAXLEN
            )

    def validate_hostname(self):
        if len(self.hostname.value) < 1:
            return _("Server name must not be empty")

        if len(self.hostname.value) > HOSTNAME_MAXLEN:
            return _("Server name too long, must be less than {limit}").format(
                limit=HOSTNAME_MAXLEN
            )

        if not re.match(HOSTNAME_REGEX, self.hostname.value):
            return _("Hostname must match HOSTNAME_REGEX: " + HOSTNAME_REGEX)

    def validate_username(self):
        username = self.username.value
        if len(username) < 1:
            return _("Username missing")

        if len(username) > USERNAME_MAXLEN:
            return _("Username too long, must be less than {limit}").format(
                limit=USERNAME_MAXLEN
            )

        if not re.match(r"[a-z_][a-z0-9_-]*", username):
            return _("Username must match USERNAME_REGEX: " + USERNAME_REGEX)

        state = self.username.widget.validation_result
        if state == UsernameValidation.SYSTEM_RESERVED:
            return _(
                'The username "{username}" is reserved for use by the system.'
            ).format(username=username)

        if state == UsernameValidation.ALREADY_IN_USE:
            return _('The username "{username}" is already in use.').format(
                username=username
            )

    def validate_password(self):
        if len(self.password.value) < 1:
            return _("Password must be set")

    def validate_confirm_password(self):
        if self.password.value != self.confirm_password.value:
            return _("Passwords do not match")


class IdentityView(BaseView):
    title = _("Profile setup")
    excerpt = _(
        "Enter the username and password you will use to log in to "
        "the system. You can configure SSH access on the next screen "
        "but a password is still needed for sudo."
    )

    def __init__(self, controller, identity_data):
        self.controller = controller

        reserved_usernames_path = resource_path("reserved-usernames")
        reserved_usernames = set()
        if os.path.exists(reserved_usernames_path):
            with open(reserved_usernames_path) as fp:
                for line in fp:
                    line = line.strip()
                    if line.startswith("#") or not line:
                        continue
                    reserved_usernames.add(line)
        else:
            reserved_usernames.add("root")

        initial = {
            "realname": identity_data.realname,
            "username": identity_data.username,
            "hostname": identity_data.hostname,
        }

        self.form = IdentityForm(controller, initial)

        self.form.confirm_password.use_as_confirmation(
            for_field=self.form.password, desc=_("Passwords")
        )

        connect_signal(self.form, "submit", self.done)

        super().__init__(
            screen(
                self.form.as_rows(),
                [self.form.done_btn],
                excerpt=_(self.excerpt),
                focus_buttons=False,
            )
        )

    def done(self, result):
        self.controller.done(
            IdentityData(
                hostname=self.form.hostname.value,
                realname=self.form.realname.value,
                username=self.form.username.value,
                crypted_password=crypt_password(self.form.password.value),
            )
        )
