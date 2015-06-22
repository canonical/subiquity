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

from urwid import (WidgetWrap, ListBox, Pile, BoxAdapter)
from subiquity.ui.lists import SimpleList
from subiquity.ui.anchors import Header, Footer, Body  # NOQA
from subiquity.ui.buttons import cancel_btn
from subiquity.ui.utils import Padding, Color


class InstallpathView(WidgetWrap):
    def __init__(self, model, cb=None):
        Header.title = "15.10"
        Header.excerpt = ("Welcome to Ubuntu! The world’s favourite platform "
                          "for clouds, clusters and amazing internet things. "
                          "This is the installer for Ubuntu on servers and "
                          "internet devices.")
        Footer.message = ("Use UP, DOWN arrow keys, and ENTER, to "
                          "navigate options..")
        self.model = model
        self.cb = cb
        self.items = []
        self.layout = [
            Header(),
            Padding.center_79(self._build_model_inputs()),
            Padding.center_20(self._build_buttons()),
            Footer()
        ]
        super().__init__(ListBox(self.layout))

    def _build_buttons(self):
        self.buttons = [
            Color.button_secondary(cancel_btn(on_press=self.cancel),
                                   focus_map='button_secondary focus'),
        ]
        return Pile(self.buttons)

    def _build_model_inputs(self):
        sl = SimpleList(self.model.install_paths)
        return BoxAdapter(sl,
                          height=len(self.model.install_paths))

    def confirm(self, button):
        if self.cb is not None:
            return self.cb(True, 'Moving to next controller.')

    def cancel(self, button):
        if self.cb is None:
            raise SystemExit('Cancelled.')
        else:
            return self.cb(False, 'Cancelled with callback.')
