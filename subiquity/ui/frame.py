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

from subiquitycore.ui.frame import SubiquityCoreUI
from subiquitycore.view import BaseView


log = logging.getLogger('subiquity.ui.frame')


class SubiquityUI(SubiquityCoreUI):

    block_input = False

    def __init__(self, app, right_icon):
        self.app = app
        self.right_icon = right_icon
        super().__init__()

    def keypress(self, size, key):
        if not self.block_input:
            return super().keypress(size, key)

    def set_body(self, widget):
        super().set_body(widget)
        if isinstance(widget, BaseView):
            for overlay in self.app.global_overlays:
                widget.show_stretchy_overlay(overlay)
