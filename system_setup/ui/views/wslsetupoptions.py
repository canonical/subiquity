# Copyright 2022 Canonical, Ltd.
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

""" WSLSetupOptions

WSLSetupOptions provides user with options to customize the setup experience.
"""

from urwid import (
    connect_signal,
)

from subiquitycore.ui.form import (
    Form,
    BooleanField,
)
from subiquitycore.ui.utils import screen
from subiquitycore.view import BaseView
from subiquity.common.types import WSLSetupOptions

CAPTION = _("Install packages for better {lang} language support")


class WSLSetupOptionsForm(Form):
    install_language_support_packages = \
        BooleanField("",
                     help=('info_minor',
                           _("Not recommended for slow internet connections."))
                     )


class WSLSetupOptionsView(BaseView):
    title = _("Enhance your experience")
    excerpt = _("Adjust the following options for a more complete experience.")

    def __init__(self, controller, configuration_data, cur_lang):
        self.controller = controller

        pkgs = configuration_data.install_language_support_packages
        initial = {"install_language_support_packages": pkgs}
        self.form = WSLSetupOptionsForm(initial=initial)
        self.form.install_language_support_packages.caption = \
            CAPTION.format(lang=cur_lang)

        connect_signal(self.form, 'submit', self.done)
        super().__init__(
            screen(
                self.form.as_rows(),
                [self.form.done_btn],
                focus_buttons=True,
                excerpt=self.excerpt,
            )
        )

    def done(self, result):
        self.controller.done(WSLSetupOptions(**self.form.as_data()))
