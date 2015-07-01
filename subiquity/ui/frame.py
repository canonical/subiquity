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
from subiquity.ui.anchors import Header, Footer, Body
import logging


log = logging.getLogger('subiquity.ui.frame')


class SubiquityUI(WidgetWrap):
    key_conversion_map = {'tab': 'down', 'shift tab': 'up'}

    def __init__(self, header=None, body=None, footer=None):
        self.header = header if header else Header()
        self.body = body if body else Body()
        self.footer = footer if footer else Footer()
        self.frame = Frame(self.body, header=self.header, footer=self.footer)
        super().__init__(self.frame)

    def keypress(self, size, key):
        key = self.key_conversion_map.get(key, key)
        return super().keypress(size, key)

    def set_header(self, title, excerpt):
        self.frame.header = Header(title, excerpt)

    def set_footer(self, message):
        self.frame.footer = Footer(message)

    def set_body(self, widget):
        self.frame.body = widget
