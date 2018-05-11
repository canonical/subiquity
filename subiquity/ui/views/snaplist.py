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

import logging

from urwid import (
    CheckBox,
    Text,
    )

from subiquitycore.ui.buttons import ok_btn, cancel_btn
from subiquitycore.ui.container import Columns
from subiquitycore.ui.utils import button_pile, Color, screen
from subiquitycore.view import BaseView


log = logging.getLogger("subiquity.views.welcome")


class SnapListView(BaseView):

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.to_install = []
        body = []
        snaps = self.model.get_snap_list()
        name_len = max([len(snap.name) for snap in snaps])
        for snap in snaps:
            body.append(Color.menu_button(Columns([
                (name_len+4, CheckBox(snap.name)),
                Text(snap.summary, wrap='clip'),
                ], dividechars=1)))
        ok = ok_btn(label=_("OK"), on_press=self.done)
        cancel = cancel_btn(label=_("Cancel"), on_press=self.done)
        super().__init__(screen(body, button_pile([ok, cancel])))

    def done(self, sender=None):
        self.controller.done(self.to_install)

    def cancel(self, sender=None):
        self.controller.cancel()
