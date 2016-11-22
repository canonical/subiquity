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

""" Locale

Provide configuration for keymaps, languages, etc.

"""
import logging
from urwid import (ListBox, Pile, Text, RadioButton)
from subiquitycore.ui.buttons import done_btn, cancel_btn
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.view import BaseView
from subiquitycore import utils

log = logging.getLogger("subiquitycore.views.locale")


class CoreLocaleView(BaseView):

    def __init__(self, model, controller, signal):
        self.model = model
        self.controller = controller
        self.signal = signal
        self.body = [
            Padding.line_break(""),
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        super().__init__(ListBox(self.body))

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def _build_model_inputs(self):
        items = []
        lang = []

        layouts = self.model.get_layouts()
        variants = self.model.get_variants()

        for layout in layouts:
            has_variant = False
            if layout[1] in variants:
                has_variant = True
            items += [ RadioButton(lang, layout[0] + ": " + str(has_variant), on_state_change=self.model.set_effective_layout, user_data=layout[1]) ]

        return Pile(items)

    def done(self, button):
        log.debug("Locale configuration: " + str(self.model))
        self.controller.done()

    def cancel(self, button):
        self.signal.prev_signal()
