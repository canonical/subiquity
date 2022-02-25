# Copyright 2021 Canonical, Ltd.
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

"""Welcome

Welcome provides user with language selection
"""

import logging

from urwid import Text

from subiquitycore.ui.buttons import forward_btn, other_btn
from subiquitycore.ui.utils import rewrap, screen
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.ui.views.serial")


SERIAL_TEXT = """

As the installer is running on a serial console, it has started in
basic mode, using only the ASCII character set and black and white
colours.

If you are connecting from a terminal emulator such as gnome-terminal
that supports unicode and rich colours you can switch to "rich mode"
which uses unicode, colours and supports many languages.

"""

SSH_TEXT = """
You can also connect to the installer over the network via SSH, which
will allow use of rich mode.
"""


class SerialView(BaseView):
    title = "Serial"

    def __init__(self, controller, ssh_info):
        self.controller = controller
        self.ssh_info = ssh_info
        super().__init__(self.make_serial())

    def make_serial(self):
        self.rich_btn = forward_btn(
                label="Continue in rich mode",
                on_press=self.rich_mode)
        self.basic_btn = forward_btn(
                label="Continue in basic mode",
                on_press=self.basic_mode)
        btns = [self.rich_btn, self.basic_btn]
        widgets = [
            Text(""),
            Text(rewrap(SERIAL_TEXT)),
            Text(""),
        ]
        if self.ssh_info:
            widgets.append(Text(rewrap(SSH_TEXT)))
            widgets.append(Text(""))
            btns.append(other_btn(
                label="View SSH instructions",
                on_press=self.ssh_help))
        return screen(widgets, btns)

    def rich_mode(self, sender):
        self.controller.done(True)

    def basic_mode(self, sender):
        self.controller.done(False)

    def ssh_help(self, sender):
        menu = self.controller.app.help_menu
        menu.ssh_info = self.ssh_info
        menu.ssh_help()
