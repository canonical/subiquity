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

from subiquitycore.controller import BaseController

from subiquity.ui.views.proxy import ProxyView

log = logging.getLogger('subiquity.controllers.proxy')


class ProxyController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.proxy
        self.answers = self.all_answers.get('Proxy', {})

    def default(self):
        title = _("Configure proxy")
        excerpt = _("If this system requires a proxy to connect to the internet, enter its details here.")
        self.ui.set_header(title, excerpt)
        self.ui.set_body(ProxyView(self.model, self))
        if 'proxy' in self.answers:
            self.done(self.answers['proxy'])

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def done(self, proxy):
        self.model.proxy = proxy
        self.signal.emit_signal('next-screen')
