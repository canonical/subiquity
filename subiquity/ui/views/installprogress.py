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
from urwid import (
    LineBox,
    Text,
    SimpleFocusListWalker,
    )

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import cancel_btn, ok_btn
from subiquitycore.ui.container import ListBox, Pile
from subiquitycore.ui.utils import button_pile, Padding

log = logging.getLogger("subiquity.views.installprogress")

class MyLineBox(LineBox):
    def format_title(self, title):
        if title:
            return [" ", title, " "]
        else:
            return ""


class ProgressView(BaseView):
    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.listwalker = SimpleFocusListWalker([])
        self.linebox = MyLineBox(ListBox(self.listwalker))
        body = [
            ('pack', Text("")),
            ('weight', 1, Padding.center_79(self.linebox)),
            ('pack', Text("")),
        ]
        self.pile = Pile(body)
        super().__init__(self.pile)

    def add_log_tail(self, text):
        for line in text.splitlines():
            self.listwalker.append(Text(line))
        self.listwalker.set_focus(len(self.listwalker) - 1)

    def clear_log_tail(self):
        self.listwalker[:] = []

    def set_status(self, text):
        self.linebox.set_title(text)

    def show_complete(self, include_exit=False):
        buttons = [
            ok_btn(label=_("Reboot Now"), on_press=self.reboot),
            ]
        if include_exit:
            buttons.append(
                cancel_btn(label=_("Exit To Shell"), on_press=self.quit))
        buttons = button_pile(buttons)

        new_pile = Pile([
                ('pack', Text("")),
                buttons,
                ('pack', Text("")),
            ])
        self.pile.contents[-1] = (new_pile, self.pile.options('pack'))
        self.pile.focus_position = len(self.pile.contents) - 1

    def reboot(self, btn):
        self.controller.reboot()

    def quit(self, btn):
        self.controller.quit()
