# Copyright 2017 Canonical, Ltd.
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

from urwid import (
    connect_signal,
    Text,
    )

from subiquitycore.ui.buttons import (
    PlainButton,
    )
from subiquitycore.ui.container import ListBox
from subiquitycore.view import BaseView

text = """The installer can guide you through partitioning a disk or, if
you prefer, you can do it manually. If you choose guided partitioning you
will still have a chance to review and modify the results."""


class GuidedFilesystemView(BaseView):

    def __init__(self, model, controller):
        self.controller = controller
        guided = PlainButton(label="Guided")
        connect_signal(guided, 'click', self.guided)
        manual = PlainButton(label="Manual")
        connect_signal(manual, 'click', self.manual)
        lb = ListBox([Text(text), guided, manual])
        super().__init__(lb)

    def manual(self, btn):
        self.controller.manual()

    def guided(self, btn):
        self.controller.guided()
