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

from urwid import (WidgetWrap, ListBox, Pile)
from subiquity.ui.anchors import Header, Footer, Body  # NOQA
from subiquity.ui.buttons import confirm_btn, cancel_btn
from subiquity.ui.utils import Padding, Color


class WelcomeView(WidgetWrap):
    def __init__(self, cb=None):
        Header.title = "Wilkommen! Bienvenue! Welcome! Zdrastvutie! Welkom!"
        Header.excerpt = "Please choose your preferred language"
        Footer.message = ("Use UP, DOWN arrow keys, and ENTER, to "
                          "select your language.")
        self.cb = cb
        self.layout = [
            Header(),
            Padding.center_20(self._build_buttons()),
            Footer()
        ]
        super().__init__(ListBox(self.layout))

    def _build_buttons(self):
        self.buttons = [
            Color.button_primary(confirm_btn(on_press=self.confirm),
                                 focus_map='button_primary focus'),
            Color.button_secondary(cancel_btn(on_press=self.cancel),
                                   focus_map='button_secondary focus'),
        ]
        return Pile(self.buttons)

    def confirm(self, button):
        if self.cb is not None:
            return self.cb(True, 'Moving to next controller.')

    def cancel(self, button):
        if self.cb is None:
            raise SystemExit('Cancelled.')
        else:
            return self.cb(False, 'Cancelled with callback.')
