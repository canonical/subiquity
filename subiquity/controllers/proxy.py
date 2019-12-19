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
import os

from subiquity.controller import SubiquityController
from subiquity.ui.views.proxy import ProxyView

log = logging.getLogger('subiquity.controllers.proxy')


class ProxyController(SubiquityController):

    model_name = "proxy"

    def start_ui(self):
        self.ui.set_body(ProxyView(self.model, self))
        if 'proxy' in self.answers:
            self.done(self.answers['proxy'])

    def cancel(self):
        self.app.prev_screen()

    def serialize(self):
        return self.model.proxy

    def deserialize(self, data):
        self.model.proxy = data

    def done(self, proxy):
        log.debug("ProxyController.done next_screen proxy=%s", proxy)
        if proxy != self.model.proxy:
            self.model.proxy = proxy
            os.environ['http_proxy'] = os.environ['https_proxy'] = proxy
            self.signal.emit_signal('network-proxy-set')
        self.configured()
        self.app.next_screen()
