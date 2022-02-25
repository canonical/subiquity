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

from urwid import Text

from subiquitycore.ui.buttons import forward_btn, other_btn
from subiquitycore.ui.container import ListBox
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import button_pile, rewrap, screen
from subiquitycore.screen import is_linux_tty
from subiquitycore.view import BaseView

from subiquity.common.resources import resource_path

log = logging.getLogger("subiquity.ui.views.welcome")


HELP = _("""
Select the language to use for the installer and to be configured in the
installed system.
""")

CLOUD_INIT_FAIL_TEXT = """
cloud-init failed to complete after 10 minutes of waiting. This
suggests a bug, which we would appreciate help understanding.  If you
could file a bug at https://bugs.launchpad.net/subiquity/+filebug and
attach the contents of /var/log, it would be most appreciated.
"""


def get_languages():
    lang_path = resource_path('languagelist')

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
        self.serial = serial
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
        back = None
        if self.serial:
            back = other_btn(_("Back"), on_press=self.controller.cancel)
        if current_index is not None:
            lb.base_widget.focus_position = current_index
        return screen(
            lb, focus_buttons=False, narrow_rows=True,
            buttons=[back] if back else None,
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
