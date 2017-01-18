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
    ListBox,
    Text,
    Pile,
    )

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import confirm_btn
from subiquitycore.ui.utils import Padding, Color

log = logging.getLogger("subiquity.views.installprogress")


class ProgressView(BaseView):
    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.error = Text("")
        self.status = Text("Running install step.")
        self.log = Text("<log goes here>")
        body = [
            ('pack', Padding.center_79(self.error)),
            ('pack', Padding.center_79(self.status)),
            ('pack', Text("")),
            ('weight', 1, Padding.center_79(LineBox(ListBox([self.log]), title="Installation logs"))),
            ('pack', Text("")),
        ]
        self.pile = Pile(body)
        super().__init__(self.pile)

    def set_log_tail(self, text):
        self.log.set_text(text)

    def set_status(self, text):
        self.status.set_text(text)

    def set_error(self, text):
        self.error.set_text(text)

    def show_complete(self):
        self.status.set_text("Finished install!")
        w = Padding.fixed_20(
            Color.button(confirm_btn(label="Reboot now",
                                     on_press=self.reboot),
                         focus_map='button focus'))

        z = Padding.fixed_20(
            Color.button(confirm_btn(label="Quit Installer",
                                     on_press=self.quit),
                         focus_map='button focus'))

        new_focus = len(self.pile.contents)
        self.pile.contents.append((w, self.pile.options('pack')))
        self.pile.contents.append((z, self.pile.options('pack')))
        self.pile.contents.append((Text(""), self.pile.options('pack')))
        self.pile.focus_position = new_focus

    def reboot(self, btn):
        self.controller.reboot()

    def quit(self, btn):
        self.controller.quit()
