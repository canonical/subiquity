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
from urwid import connect_signal

from subiquitycore.view import BaseView
from subiquitycore.ui.form import (
    Form,
)


log = logging.getLogger('subiquity.ui.ssh')


class SSHForm(Form):

    cancel_label = _("Back")


class SSHView(BaseView):

    title = _("SSH Setup")
    excerpt = _("You can choose to install the OpenSSH server package to "
                "enable secure remote access to your server.")

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller

        self.form = SSHForm(initial={})

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        super().__init__(self.form.as_screen(excerpt=_(self.excerpt)))

    def done(self, sender):
        log.debug("User input: {}".format(self.form.as_data()))
        self.controller.done(self.form.as_data())

    def cancel(self, result=None):
        self.controller.cancel()
