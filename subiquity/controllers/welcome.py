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
from subiquity.ui.views import WelcomeView

log = logging.getLogger('subiquity.controllers.welcome')


class WelcomeController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.locale
        self.answers = self.all_answers.get("Welcome", {})
        log.debug("Welcome: answers=%s", self.answers)

    def default(self):
        view = WelcomeView(self.model, self)
        self.ui.set_body(view)
        if 'lang' in self.answers:
            self.model.switch_language(self.answers['lang'])
            self.done()

    def done(self):
        self.signal.emit_signal('next-screen')

    def cancel(self):
        # Can't go back from here!
        pass
