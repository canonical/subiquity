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

""" Welcome

Welcome provides user with language selection

"""
import logging

from subiquitycore.ui.buttons import done_btn
from subiquitycore.ui.utils import button_pile, screen
from subiquitycore.view import BaseView

log = logging.getLogger("console_conf.views.welcome")


class WelcomeView(BaseView):
    title = "Ubuntu Core"
    excerpt = (
        "Configure the network and setup an administrator "
        "account on this all-snap Ubuntu Core system."
    )

    def __init__(self, controller):
        self.controller = controller
        super().__init__(
            screen(
                rows=[],
                buttons=button_pile([done_btn("OK", on_press=self.confirm)]),
                focus_buttons=True,
                excerpt=self.excerpt,
            )
        )

    def confirm(self, result):
        self.controller.done()


class ChooserWelcomeView(WelcomeView):
    excerpt = (
        "System mode selection triggered. Proceed to select one of available "
        "systems and actions."
    )

    def __init__(self, controller):
        super().__init__(controller)

        current = controller.model.current
        if current is not None:
            self.title = current.model.display_name
