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

from urwid import Text

from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import button_pile

log = logging.getLogger('subiquity.ui.view.global_extra')


def close_btn(parent):
    return other_btn(
        _("Close"), on_press=lambda sender: parent.remove_overlay())


class GlobalExtraStretchy(Stretchy):

    def __init__(self, app, parent):
        self.app = app
        self.parent = parent

        btns = []
        btns.append(other_btn("button"))

        widgets = [
            button_pile(btns),
            Text(""),
            button_pile([close_btn(parent)]),
            ]
        super().__init__(_("Available Actions"), widgets, 0, 0)
