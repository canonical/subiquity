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

from gettext import install
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


class WSLSetupOptionsForm(Form):
    def __init__(self, initial):
        super().__init__(initial=initial)
        connect_signal(self.install_language_support_packages.widget, "change",
                       self.toggle_help)


=======
class WSLSetupOptionsForm(Form):
>>>>>>> 18290ac4 (Fixed help strings)
    install_language_support_packages = \
        BooleanField(_("Install packages for better language support"),
                     help=_("Not recommended for slow internet connections."))



class WSLSetupOptionsView(BaseView):
    title = _("Enhance your experience")
    excerpt = _("Adjust the following options for a more complete experience.")

    def __init__(self, controller, configuration_data):
        self.controller = controller

        initial = {
            'install_language_support_packages':
                configuration_data.install_language_support_packages,
        }
        self.form = WSLSetupOptionsForm(initial=initial)

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

