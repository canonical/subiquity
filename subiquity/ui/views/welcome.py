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

""" Welcome

Welcome provides user with language selection

"""
import logging

from subiquitycore.ui.buttons import forward_btn
from subiquitycore.ui.container import ListBox
from subiquitycore.ui.utils import screen
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.views.welcome")

help_text = _("""
Select your language using the up and down arrows and press enter or
space to continue.""")


class WelcomeView(BaseView):
    title = "Willkommen! Bienvenue! Welcome! Добро пожаловать! Welkom!"
    footer = _("Use UP, DOWN and ENTER keys to select your language.")

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        super().__init__(screen(
            self._build_model_inputs(),
            buttons=None,
            narrow_rows=True,
            excerpt=_("Please choose your preferred language.")))

    def local_help(self):
        return _("Language Selection"), _(help_text)

    def _build_model_inputs(self):
        btns = []
        current_index = None
        for i, (code, native) in enumerate(self.model.get_languages()):
            if code == self.model.selected_language:
                current_index = i
            btns.append(forward_btn(label=native, on_press=self.confirm,
                                    user_arg=code))

        lb = ListBox(btns)
        if current_index is not None:
            lb.base_widget.focus_position = current_index
        return lb

    def confirm(self, sender, code):
        log.debug('WelcomeController %s', code)
        self.controller.done(code)
