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

""" Base Frame Widget """

import logging

from urwid import (
    Text,
    )
from subiquitycore.ui.anchors import Header
from subiquitycore.ui.container import (
    ListBox,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.utils import Color


log = logging.getLogger('subiquitycore.ui.frame')


class SubiquityCoreUI(WidgetWrap):

    right_icon = Text("")

    def __init__(self):
        self.header = Header("", self.right_icon)
        self.pile = Pile([
            ('pack', self.header),
            ListBox([Text("")]),
            ])
        self.pile.focus_position = 1
        super().__init__(Color.body(self.pile))

    def _assign_contents(self, i, w):
        self.pile.contents[i] = (w, self.pile.contents[i][1])

    def set_header(self, title=None):
        self._assign_contents(0, Header(title, self.right_icon))

    @property
    def body(self):
        return self.pile.contents[1][0]

    def set_body(self, widget):
        self.set_header(_(widget.title))
        self._assign_contents(1, widget)
