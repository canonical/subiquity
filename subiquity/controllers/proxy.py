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

from subiquitycore.controller import BaseController

from subiquity.ui.views.proxy import ProxyView

log = logging.getLogger('subiquity.controllers.proxy')


class ProxyController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.proxy
        self.answers = self.all_answers.get('Proxy', {})

    def default(self):
        self.ui.set_body(ProxyView(self.model, self))
        if 'proxy' in self.answers:
            self.done(self.answers['proxy'])

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def serialize(self):
        return self.model.proxy

    def deserialize(self, data):
        self.model.proxy = data

    def done(self, proxy):
        _proxy_file = '/etc/profile.d/subiquity-proxy.sh'
        log.debug("ProxyController.done next-screen proxy=%s", proxy)
        if proxy != self.model.proxy:
            self.model.proxy = proxy
            os.environ['http_proxy'] = os.environ['https_proxy'] = proxy
            if os.path.exists(_proxy_file):
                os.unlink(_proxy_file)
            if proxy:
                with open(_proxy_file, 'w') as f:
                    f.write('''#!/bin/sh
export http_proxy={http_proxy}
export https_proxy={http_proxy}
'''.format(**os.environ))
            self.signal.emit_signal('network-proxy-set')
        self.signal.emit_signal('next-screen')
