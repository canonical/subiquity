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

from subiquitycore.controller import BaseController
from console_conf.models import ProxyModel

from console_conf.ui.views import ProxyView

log = logging.getLogger('console_conf.controllers.identity')

class ProxyController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = ProxyModel(self.opts)

    def default(self):
        title = "Proxy setup"
        excerpt = "Set up a http/https proxy, if required. Leave blank if not."
        footer = ""
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 40)
        self.ui.set_body(ProxyView(self.model, self, self.opts))

    def done(self, proxy):
        self.model.set_proxy(proxy)
        self.signal.emit_signal('next-screen')

    def cancel(self):
        self.signal.emit_signal('prev-screen')
