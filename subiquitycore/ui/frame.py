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

from urwid import (
    Frame,
    Text,
    WidgetWrap,
    )
from subiquitycore.ui.anchors import Header, Footer
from subiquitycore.ui.container import ListBox
from subiquitycore.ui.utils import Color
import logging


log = logging.getLogger('subiquitycore.ui.frame')


class SubiquityUI(WidgetWrap):

    def __init__(self):
        self.header = Header("")
        self.footer = Footer("", 0, 1)
        self.frame = Frame(
            ListBox([Text("")]),
            header=self.header, footer=self.footer)
        self.progress_current = 0
        self.progress_completion = 0
        super().__init__(Color.body(self.frame))

    def keypress(self, size, key):
        return super().keypress(size, key)

    def set_header(self, title=None):
        self.frame.header = Header(title)

    def set_footer(self, message):
        self.frame.footer = Footer(message, self.progress_current,
                                   self.progress_completion)

    def set_body(self, widget):
        self.set_header(_(widget.title))
        self.frame.body = widget
        self.set_footer(_(widget.footer))
