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

from subiquity.controller import SubiquityTuiController
from subiquity.ui.views.welcome import get_languages, WelcomeView
from subiquity.ui.views.help import get_global_addresses


log = logging.getLogger('subiquity.controllers.welcome')


class WelcomeController(SubiquityTuiController):

    autoinstall_key = model_name = "locale"
    autoinstall_schema = {'type': 'string'}
    autoinstall_default = 'en_US.UTF-8'

    def interactive(self):
        return self.app.interactive()

    def load_autoinstall_data(self, data):
        os.environ["LANG"] = data

    def start(self):
        lang = os.environ.get("LANG")
        if lang is not None and lang.endswith(".UTF-8"):
            lang = lang.rsplit('.', 1)[0]
        for code, name in get_languages():
            if code == lang:
                self.model.switch_language(code)
                break
        else:
            self.model.selected_language = lang

    def make_ui(self):
        language = self.model.selected_language
        serial = self.app.opts.run_on_serial
        if serial:
            ips = get_global_addresses(self.app)
        else:
            ips = None
        return WelcomeView(self, language, serial, ips)

    def run_answers(self):
        if 'lang' in self.answers:
            self.done(self.answers['lang'])

    def done(self, code):
        log.debug("WelcomeController.done %s next_screen", code)
        self.signal.emit_signal('l10n:language-selected', code)
        self.model.switch_language(code)
        self.configured()
        self.app.next_screen()

    def cancel(self):
        # Can't go back from here!
        pass

    def serialize(self):
        return self.model.selected_language

    def deserialize(self, data):
        self.model.switch_language(data)

    def make_autoinstall(self):
        return self.model.selected_language
