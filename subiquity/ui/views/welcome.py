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
from urwid import BoxAdapter, Text
from subiquitycore.ui.lists import SimpleList
from subiquitycore.ui.buttons import menu_btn, ok_btn
from subiquitycore.ui.container import ListBox, Pile
from subiquitycore.ui.utils import connect_signal, Padding, Color
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.views.welcome")


class WelcomeView(BaseView):

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        super().__init__(ListBox([
            Padding.center_50(self._build_model_inputs()),
            Text(""),
            Padding.center_79(Text("(More language choices will appear in time)"))]))

    def _build_buttons(self):
        self.buttons = [
            Color.button(ok_btn(on_press=self.confirm)),
        ]
        return Pile(self.buttons)

    def _build_model_inputs(self):
        sl = []
        for lang, code in self.model.get_languages():
            btn = menu_btn(label=lang)
            connect_signal(btn, 'click', self.confirm, code)
            sl.append(btn)

        return BoxAdapter(SimpleList(sl), height=len(sl))

    def confirm(self, sender, code):
        self.model.selected_language = code
        log.debug('calling installpath')
        self.controller.done()
