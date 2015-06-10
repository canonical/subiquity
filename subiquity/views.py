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

from urwid import (WidgetWrap, ListBox, AttrWrap, Columns, Text,
                   # emitters
                   signals, emit_signal)
from subiquity.ui.anchors import Header, Footer, Body  # NOQA
from subiquity.ui.buttons import confirm_btn, cancel_btn
from subiquity.ui.utils import Padding


class StartView(WidgetWrap):
    __metaclass__ = signals.MetaSignals
    signals = ['done']

    def __init__(self):
        Header.title = "SUbiquity - Ubiquity for Servers"
        self.layout = [
            Header(),
            Text(""),
            Text("Begin the installation", align='center'),
            Padding.center(self._build_buttons()),
            Footer()
        ]
        super().__init__(ListBox(self.layout))

    def _build_buttons(self):
        self.buttons = [
            AttrWrap(confirm_btn(on_press=self.confirm),
                     'button_primary', 'button_primary focus'),
            AttrWrap(cancel_btn(on_press=self.cancel),
                     'button_secondary', 'button_secondary focus'),
        ]
        return Columns(self.buttons)

    def confirm(self, button):
        emit_signal(self, 'done', True)

    def cancel(self, button):
        emit_signal(self, 'done', False)
