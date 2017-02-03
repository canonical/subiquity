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

from urwid import Frame, WidgetWrap
from subiquitycore.ui.anchors import Header, Footer, Body
import logging


log = logging.getLogger('subiquitycore.ui.frame')


class SubiquityUI(WidgetWrap):

    def __init__(self, header=None, body=None, footer=None):
        self.header = header if header else Header()
        self.body = body if body else Body()
        self.footer = footer if footer else Footer()
        self.frame = Frame(self.body, header=self.header, footer=self.footer)
        super().__init__(self.frame)

    def keypress(self, size, key):
        return super().keypress(size, key)

    def set_header(self, title=None, excerpt=None):
        self.frame.header = Header(title, excerpt)

    def set_footer(self, message, completion=0):
        self.frame.footer = Footer(message, completion)

    def set_body(self, widget):
        self.frame.body = widget
