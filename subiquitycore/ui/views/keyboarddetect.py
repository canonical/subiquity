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

""" KeyboardDetect

Allow the user to use keyboard detection

"""
import logging
from urwid import (ListBox, Pile, Text, RadioButton)
from subiquitycore.ui.buttons import menu_btn, cancel_btn
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.view import BaseView
from subiquitycore import utils

log = logging.getLogger("subiquitycore.views.keyboard.detect")


class KeyboardDetectView(BaseView):

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.body = [
            Padding.line_break(""),
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        super().__init__(ListBox(self.body))

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)

        buttons = [
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def _build_model_inputs(self):
        detect = menu_btn(label="Auto-detect keyboard", on_press=self.do_detect)
        pick = menu_btn(label="Select from a list", on_press=self.controller.pick_layout)

        buttons = [
            Color.button(detect, focus_map='button focus'),
            Color.button(pick, focus_map='button focus')
        ]

        return Pile(buttons)

    def do_detect(self, btn):
        log.debug("do detect")

    def done(self, button):
        pass

    def cancel(self, button):
        self.controller.cancel()

