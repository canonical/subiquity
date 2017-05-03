# Copyright 2017 Canonical, Ltd.
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
from urllib.parse import urlparse

from urwid import connect_signal

from subiquitycore.ui.container import ListBox
from subiquitycore.ui.form import StringField, Form
from subiquitycore.ui.utils import Padding
from subiquitycore.view import BaseView

log = logging.getLogger("console_conf.ui.views.proxy")


class URLField(StringField):
    def validate(self, value):
        log.debug('validating %r', value)
        if value == "":
            return None
        parsed = urlparse(value)
        log.debug('validating %r', parsed)
        if not parsed.scheme or not parsed.netloc:
            return "This does not look like a URL"

class ProxyForm(Form):
    proxy = URLField("Proxy URL:")

class ProxyView(BaseView):

    def __init__(self, model, controller, opts):
        self.model = model
        self.controller = controller
        self.opts = opts
        self.form = ProxyForm()
        self.form.proxy.value = model.get_proxy()
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        body = [
            Padding.center_79(self.form.as_rows(self)),
            Padding.line_break(""),
            Padding.fixed_10(self.form.buttons)
        ]
        super().__init__(ListBox(body))

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key == 'enter':
            self.form.proxy.validate()
            if not self.form.proxy.in_error:
                self.done(None)
            return None
        else:
            return key

    def cancel(self, button=None):
        self.controller.cancel()

    def done(self, button):
        self.controller.done(self.form.proxy.value)
