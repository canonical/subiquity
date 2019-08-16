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
import os

from subiquitycore.controller import BaseController

from subiquity.ui.views import WelcomeView


log = logging.getLogger('subiquity.controllers.welcome')


class WelcomeController(BaseController):

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model.locale
        log.debug("Welcome: answers=%s", self.answers)

    def start(self):
        lang = os.environ.get("LANG")
        if lang.endswith(".UTF-8"):
            lang = lang.rsplit('.', 1)[0]
        for code, name in self.model.supported_languages:
            if code == lang:
                self.model.switch_language(code)

    def default(self):
        view = WelcomeView(self.model, self)
        self.ui.set_body(view)
        if 'lang' in self.answers:
            self.done(self.answers['lang'])

    def done(self, code):
        log.debug("WelcomeController.done %s next-screen")
        self.signal.emit_signal('l10n:language-selected', code)
        self.model.switch_language(code)
        self.signal.emit_signal('next-screen')

    def cancel(self):
        # Can't go back from here!
        pass

    def serialize(self):
        return self.model.selected_language

    def deserialize(self, data):
        self.model.switch_language(data)
