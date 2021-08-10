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

from urwid import (
    connect_signal,
    )


from subiquity.common.types import IdentityData
from subiquity.ui.views.identity import IdentityForm, IdentityView, setup_password_validation
from subiquitycore.ui.form import Form
from subiquitycore.ui.utils import screen
from subiquitycore.utils import crypt_password
from subiquitycore.view import BaseView


class WSLIdentityForm(Form):

    realname = IdentityForm.realname
    username = IdentityForm.username
    username.help = _("The username does not need to match your Windows username")
    password = IdentityForm.password
    confirm_password = IdentityForm.confirm_password

    def __init__(self, initial):
        self.identityForm = IdentityForm([], initial)
        super().__init__(initial=initial)

    def validate_realname(self):
        self.identityForm.validate_realname()

    def validate_username(self):
        self.identityForm.validate_username()

    def validate_password(self):
        self.identityForm.validate_password()

    def validate_confirm_password(self):
        self.identityForm.validate_confirm_password()


class WSLIdentityView(BaseView):
    title = IdentityView.title
    excerpt = _("Please create a default UNIX user account. "
                "For more information visit: https://aka.ms/wslusers")

    def __init__(self, controller, identity_data):
        self.controller = controller

        initial = {
            'realname': identity_data.realname,
            'username': identity_data.username,
            }

        self.form = WSLIdentityForm(initial)

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
