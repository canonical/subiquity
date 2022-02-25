# Copyright 2019 Canonical, Ltd.
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
    Text,
    )

from subiquitycore.ui.buttons import (
    other_btn,
    )
from subiquitycore.ui.spinner import (
    Spinner,
    )
from subiquitycore.ui.utils import (
    button_pile,
    screen,
    )
from subiquitycore.view import BaseView


log = logging.getLogger("subiquity.ui.views.filesystem.probing")


class SlowProbing(BaseView):

    title = _("Waiting for storage probing to complete")

    def __init__(self, controller):
        self.controller = controller
        self.spinner = Spinner(aio_loop=controller.app.aio_loop, style="dots")
        self.spinner.start()
        super().__init__(screen(
            [
                Text(_("The installer is probing for block devices to install "
                       "to. Please wait until it completes.")),
                Text(""),
                self.spinner,
            ],
            [other_btn(_("Back"), on_press=self.cancel)]
            ))

    def cancel(self, result=None):
        self.controller.cancel()


fail_text = _(
    "Unfortunately probing for devices to install to failed. Please report a "
    "bug on Launchpad, and if possible include the contents of the "
    "/var/log/installer directory.")


class ProbingFailed(BaseView):

    title = _("Probing for devices to install to failed")

    def __init__(self, controller, error_ref):
        self.controller = controller
        self.error_ref = error_ref
        super().__init__(screen([
            Text(_(fail_text)),
            Text(""),
            button_pile(
                [other_btn(_("Show Error Report"), on_press=self.show_error)]),
            ],
            [other_btn(_("Back"), on_press=self.cancel)]))

    def cancel(self, result=None):
        self.controller.cancel()

    def show_error(self, sender=None):
        self.controller.app.show_error_report(self.error_ref)
