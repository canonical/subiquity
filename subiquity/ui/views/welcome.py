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
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import button_pile, rewrap, screen
from subiquitycore.screen import is_linux_tty
from subiquitycore.view import BaseView

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

CLOUD_INIT_FAIL_TEXT = """
cloud-init failed to complete after 10 minutes of waiting. This
suggests a bug, which we would appreciate help understanding.  If you
could file a bug at https://bugs.launchpad.net/subiquity/+filebug and
attach the contents of /var/log, it would be most appreciated.
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

    def __init__(self, controller, cur_lang, serial):
        self.controller = controller
        self.cur_lang = cur_lang
        if serial and not controller.app.rich_mode:
            self.title = "Welcome!"
        super().__init__(self.make_language_choices())

    def make_language_choices(self):
        btns = []
        current_index = None
        langs = get_languages()
        cur = self.cur_lang
        if cur in ["C.UTF-8", None]:
            cur = "en_US.UTF-8"
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

    def choose_language(self, sender, code):
        log.debug('WelcomeView %s', code)
        self.controller.done(code)

    def local_help(self):
        return _("Help choosing a language"), _(HELP)


class CloudInitFail(Stretchy):
    def __init__(self, app):
        self.app = app
        self.shell_btn = other_btn(
            _("Switch to a shell"), on_press=self._debug_shell)
        self.close_btn = other_btn(
            _("Close"), on_press=self._close)
        widgets = [
            Text(rewrap(_(CLOUD_INIT_FAIL_TEXT))),
            Text(''),
            button_pile([self.shell_btn, self.close_btn]),
            ]
        super().__init__(
            "",
            widgets,
            stretchy_index=0,
            focus_index=2)

    def _debug_shell(self, sender):
        self.app.debug_shell()

    def _close(self, sender):
        self.app.remove_global_overlay(self)


class SerialChoices(Stretchy):
    def __init__(self, app, ssh_info):
        self.app = app
        btns = [
            other_btn(
                label="Switch to rich mode",
                on_press=self.enable_rich),
            forward_btn(
                label="Continue in basic mode",
                on_press=self._close),
            ]
        widgets = [
            Text(""),
            Text(rewrap(SERIAL_TEXT)),
            Text(""),
        ]
        if ssh_info:
            widgets.append(Text(rewrap(SSH_TEXT)))
            widgets.append(Text(""))
            btns.insert(1, other_btn(
                label="View SSH instructions",
                on_press=self.ssh_help,
                user_arg=ssh_info))
        widgets.append(button_pile(btns))
        focus_index = len(widgets) - 1
        super().__init__(
            "",
            widgets,
            stretchy_index=0,
            focus_index=focus_index)

    def _close(self, sender=None):
        self.app.remove_global_overlay(self)

    def enable_rich(self, sender):
        self.app.toggle_rich()
        self._close()

    def ssh_help(self, sender, ssh_info):
        menu = self.app.help_menu
        menu.ssh_info = ssh_info
        menu.ssh_help()
