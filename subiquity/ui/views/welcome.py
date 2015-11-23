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
import gettext
from urwid import (ListBox, Pile, BoxAdapter)
from subiquity.ui.lists import SimpleList
from subiquity.ui.buttons import menu_btn, cancel_btn
from subiquity.ui.utils import Padding, Color
from subiquity.view import ViewPolicy

log = logging.getLogger("subiquity.views.welcome")


class WelcomeView(ViewPolicy):
    def __init__(self, model, signal):
        self.model = model
        self.signal = signal
        self.items = []
        self.body = [
            Padding.center_50(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_15(self._build_buttons()),
        ]
        super().__init__(ListBox(self.body))

    def _build_buttons(self):
        self.buttons = [
            Color.button(cancel_btn(on_press=self.cancel),
                         focus_map='button focus'),
        ]
        return Pile(self.buttons)

    def _build_model_inputs(self):
        sl = []
        for lang in self.model.get_menu():
            sl.append(Color.menu_button(
                menu_btn(label=lang, on_press=self.confirm),
                focus_map="menu_button focus"))
        return BoxAdapter(SimpleList(sl),
                          height=len(sl))

    def confirm(self, result):
        self.model.set_language(result.label)
        log.debug('calling installpath')
        self.signal.emit_signal('menu:installpath:main')

    def cancel(self, button):
        raise SystemExit("No language selected, exiting as there are no "
                         "more previous controllers to render.")
