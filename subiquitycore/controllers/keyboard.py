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

from subiquitycore.controller import BaseController, view
from subiquitycore.models import KeyboardModel
from subiquitycore.ui.views import (KeyboardDetectView,
                                    KeyboardLayoutView,
                                    KeyboardVariantView)
from subiquitycore.ui.dummy import DummyView

log = logging.getLogger('subiquitycore.controllers.keyboard')


class KeyboardController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = KeyboardModel(self.opts)

    def default(self):
        title = "Keyboard setup"
        excerpt = ("Please select your keyboard model:")
        footer = ""
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 40)
        self.ui.set_body(self.view)

    def default(self):
        self.view_stack = []
        self.start()

    def cancel(self):
        if len(self.view_stack) <= 1:
            self.signal.emit_signal('prev-screen')
        else:
            self.prev_view()

    def done(self):
        log.debug("Keyboard configuration: " + str(self.model))
        self.signal.emit_signal('next-screen')

    @view
    def start(self):
        title = "Language setup"
        excerpt = ("Do you want to detect the keyboard or select it from a list?")
        footer = ""
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 40)
        self.ui.set_body(KeyboardDetectView(self.model, self))

    @view
    def pick_layout(self, button=None):
        self.ui.set_header("Please select your keyboard layout:")
        self.ui.set_body(KeyboardLayoutView(self.model, self))

    @view
    def pick_variant(self):
        self.ui.set_header("Select your layout variant:")
        self.ui.set_body(KeyboardVariantView(self.model, self))

