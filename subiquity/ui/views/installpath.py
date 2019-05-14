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

""" Install Path

Provides high level options for Ubuntu install

"""
import binascii
import logging
import re

from urwid import connect_signal, Text

from subiquitycore.ui.buttons import back_btn, forward_btn
from subiquitycore.ui.utils import button_pile, screen
from subiquitycore.view import BaseView
from subiquitycore.ui.interactive import (
    PasswordEditor,
    )
from subiquity.ui.views.identity import (
    UsernameField,
    PasswordField,
    USERNAME_MAXLEN,
    )
from subiquitycore.ui.form import (
    Form,
    simple_field,
    URLField,
    WantsToKnowFormField,
)

from subiquitycore.lsb_release import lsb_release

log = logging.getLogger('subiquity.installpath')


class InstallpathView(BaseView):
    title = "Ubuntu {}"

    excerpt = _("Welcome to Ubuntu! The world's favourite platform "
                "for clouds, clusters, and amazing internet things. "
                "This is the installer for Ubuntu on servers and "
                "internet devices.")
    footer = _("Use UP, DOWN arrow keys, and ENTER, to "
               "navigate options")

    def __init__(self, model, controller):
        self.title = self.title.format(
            lsb_release().get('release', 'Unknown Release'))
        self.model = model
        self.controller = controller
        self.items = []
        back = back_btn(_("Back"), on_press=self.cancel)
        super().__init__(screen(
            [self._build_choices(), Text("")], [back],
            focus_buttons=False, excerpt=_(self.excerpt)))

    def _build_choices(self):
        choices = []
        focus_position = 0
        for i, (label, path) in enumerate(self.model.paths):
            log.debug("Building inputs: {}".format(path))
            choices.append(
                forward_btn(
                    label=label, on_press=self.confirm, user_arg=path))
            if path == self.model.path:
                focus_position = i
        bp = button_pile(choices)
        bp.base_widget.focus_position = focus_position
        return bp

    def confirm(self, sender, path):
        self.controller.choose_path(path)

    def cancel(self, button=None):
        self.controller.cancel()

