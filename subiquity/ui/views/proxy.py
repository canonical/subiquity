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

""" Install Path

Provides high level options for Ubuntu install

"""
import logging
from urwid import connect_signal

from subiquitycore.view import BaseView
from subiquitycore.ui.form import (
    Form,
    URLField,
)


log = logging.getLogger('subiquity.installpath')

proxy_help = _("If you need to use a HTTP proxy to access the outside world, "
               "enter the proxy information here. Otherwise, leave this blank."
               "\n\nThe proxy information should be given in the standard "
               "form of \"http://[[user][:pass]@]host[:port]/\".")


class ProxyForm(Form):

    cancel_label = _("Back")

    url = URLField(_("Proxy address:"), help=proxy_help)


class ProxyView(BaseView):

    title = _("Configure proxy")
    excerpt = _("If this system requires a proxy to connect to the internet, "
                "enter its details here.")

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller

        self.form = ProxyForm(initial={'url': self.model.proxy})

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        super().__init__(self.form.as_screen(excerpt=_(self.excerpt)))

    def done(self, result):
        log.debug("User input: {}".format(result.as_data()))
        self.controller.done(result.url.value)

    def cancel(self, result=None):
        self.controller.cancel()
