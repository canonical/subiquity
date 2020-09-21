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

"""Welcome

Welcome provides user with language selection
"""

import logging
import os

from urwid import Text

from subiquitycore.ui.buttons import forward_btn, other_btn
from subiquitycore.ui.container import ListBox
from subiquitycore.ui.utils import button_pile, rewrap, screen
from subiquitycore.screen import is_linux_tty
from subiquitycore.view import BaseView

from subiquity.ui.views.help import (
    get_installer_password,
    )

log = logging.getLogger("subiquity.views.welcome")


HELP = _("""
Select the language to use for the installer and to be configured in the
installed system.
""")

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


def get_languages():
    base = os.environ.get("SNAP", ".")
    lang_path = os.path.join(base, "languagelist")

    languages = []
    with open(lang_path) as lang_file:
        for line in lang_file:
            level, code, name = line.strip().split(':')
            if is_linux_tty() and level != "console":
                continue
            languages.append((code, name))
    languages.sort(key=lambda x: x[1])
    return languages


class WelcomeView(BaseView):
    title = "Willkommen! Bienvenue! Welcome! Добро пожаловать! Welkom!"

    def __init__(self, controller, cur_lang, serial, ips):
        self.controller = controller
        self.cur_lang = cur_lang
        if serial and not controller.app.rich_mode:
            s = self.make_serial_choices(ips)
            self.title = "Welcome!"
        else:
            s = self.make_language_choices()
        super().__init__(s)

    def make_language_choices(self):
        btns = []
        current_index = None
        langs = get_languages()
        cur = self.cur_lang
        if cur in ["C", None]:
            cur = "en_US"
        for i, (code, native) in enumerate(langs):
            log.debug("%s", (code, cur))
            if code == cur:
                current_index = i
            btns.append(
                forward_btn(
                    label=native,
                    on_press=self.choose_language,
                    user_arg=code))

        lb = ListBox(btns)
        if current_index is not None:
            lb.base_widget.focus_position = current_index
        return screen(
            lb, buttons=None, narrow_rows=True,
            excerpt=_("Use UP, DOWN and ENTER keys to select your language."))

    def make_serial_choices(self, ips):
        ssh_password = get_installer_password(self.controller.opts.dry_run)
        btns = [
            other_btn(
                label="Switch to rich mode",
                on_press=self.enable_rich),
            forward_btn(
                label="Continue in basic mode",
                on_press=self.choose_language,
                user_arg='C'),
            ]
        widgets = [
            Text(""),
            Text(rewrap(SERIAL_TEXT)),
            Text(""),
        ]
        if ssh_password and ips:
            widgets.append(Text(rewrap(SSH_TEXT)))
            widgets.append(Text(""))
            btns.insert(1, other_btn(
                label="View SSH instructions",
                on_press=self.ssh_help,
                user_arg=ssh_password))
        widgets.extend([
            button_pile(btns),
            ])
        lb = ListBox(widgets)
        return screen(lb, buttons=None)

    def enable_rich(self, sender):
        self.controller.app.toggle_rich()
        self.title = self.__class__.title
        self.controller.ui.set_header(self.title)
        self._w = self.make_language_choices()

    def ssh_help(self, sender, password):
        menu = self.controller.app.help_menu
        menu.ssh_password = password
        menu.ssh_help()

    def choose_language(self, sender, code):
        log.debug('WelcomeView %s', code)
        self.controller.done(code)

    def local_help(self):
        return _("Help choosing a language"), _(HELP)
