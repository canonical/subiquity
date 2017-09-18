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

from urwid import WidgetWrap
from subiquitycore.ui.anchors import Header, Footer, Body
from subiquitycore.ui.container import Pile
import logging


log = logging.getLogger('subiquitycore.ui.frame')


class SubiquityUI(WidgetWrap):

    def __init__(self, header=None, body=None, footer=None):
        self.header = header if header else Header()
        self.body = body if body else Body()
        self.footer = footer if footer else Footer()
        self.frame = Pile([
            ('pack', self.header),
            self.body,
            ('pack', self.footer),
            ])
        super().__init__(self.frame)

    def keypress(self, size, key):
        if key in ['ctrl x']:
            self.frame.contents[1][0].controller.signal.emit_signal('control-x-quit')
            return None
        return super().keypress(size, key)

    def set_header(self, title=None, excerpt=None):
        self.frame.contents[0] = (Header(title, excerpt), self.frame.options('pack'))

    def set_footer(self, message, completion=0, leftbutton=None, rightbutton=None):
        self.frame.contents[2] = (Footer(message, completion, leftbutton, rightbutton), self.frame.options('pack'))

    def set_body(self, widget, footer_msg=None, completion=0):
        self.frame.contents[1] = (widget, self.frame.options())
        self.frame.focus_position = 1
        if footer_msg is not None:
            self.set_footer(footer_msg, completion, widget.left_button, widget.right_button)
