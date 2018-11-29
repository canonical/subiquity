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
from subiquity.ui.views.ssh import SSHView

log = logging.getLogger('subiquity.controllers.ssh')


class SSHController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.ssh
        self.answers = self.all_answers.get('SSH', {})

    def default(self):
        self.ui.set_body(SSHView(self.model, self))
        #if self.answers:
        #    self.done(self.answers)

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def done(self, result):
        #self.model.install_server = result['install_server']
        #self.model.authorized_keys = result['authorized_keys']
        #self.model.pwauth = result['pwauth']
        self.signal.emit_signal('installprogress:identity-config-done')
        self.signal.emit_signal('next-screen')
