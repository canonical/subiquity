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

from subiquitycore.view import BaseView
from subiquitycore.ui.utils import SomethingFailed
from subiquitycore.ui.form import (
    Form,
    EmailField,
)


log = logging.getLogger("console_conf.views.identity")

sso_help = ("If you do not have an account, visit "
            "https://login.ubuntu.com to create one.")


class IdentityForm(Form):
    cancel_label = "Back"

    email = EmailField("Email address:", help=sso_help)


class IdentityView(BaseView):
    title = "Profile setup"
    excerpt = "Enter an email address from your account in the store."

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.form = IdentityForm()

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        super().__init__(self.form.as_screen(focus_buttons=False,
                                             excerpt=_(self.excerpt)))

    def cancel(self, button=None):
        self.controller.cancel()

    def done(self, result):
        self.controller.identity_done(result.email.value)

    def snap_create_user_failed(self, msg, stderr):
        self.show_stretchy_overlay(SomethingFailed(self, msg, stderr))
