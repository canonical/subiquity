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
from subiquity.ui.views.mirror import MirrorView

log = logging.getLogger('subiquity.controllers.mirror')


class MirrorController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.mirror
        self.answers = self.all_answers.get('Mirror', {})

    def default(self):
        self.ui.set_body(MirrorView(self.model, self))
        if 'mirror' in self.answers:
            self.done(self.answers['mirror'])

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def serialize(self):
        return self.model.mirror

    def deserialize(self, data):
        self.model.mirror = data

    def done(self, mirror):
        if mirror != self.model.mirror:
            self.model.mirror = mirror
        self.signal.emit_signal('next-screen')
