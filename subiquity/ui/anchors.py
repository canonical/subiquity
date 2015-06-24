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

from urwid import WidgetWrap, Pile, Text
from subiquity.ui.utils import Padding, Color
from subiquity.ui.lists import SimpleList


class Header(WidgetWrap):
    """ Header Widget

    This widget uses the style key `frame_header`

    :param str title: Title of Header
    :returns: Header()
    """

    def __init__(self, title="Ubuntu Server Installer", excerpt=""):
        title_widget = Padding.center_79(Color.body(Text(title)))
        excerpt_widget = Padding.center_79(Color.body(Text(excerpt)))
        pile = Pile([Text(""),
                     title_widget,
                     Text(""),
                     excerpt_widget,
                     Text("")])
        super().__init__(pile)


class Footer(WidgetWrap):
    """ Footer widget

    Style key: `frame_footer`

    """

    def __init__(self, message=""):
        message_widget = Padding.center_79(Color.body(Text(message)))
        status = Pile([Padding.line_break(""), message_widget])
        super().__init__(status)


class Body(WidgetWrap):
    """ Body widget
    """

    def __init__(self):
        text = [
            Padding.line_break(""),
            Padding.center_79(
                Text("Welcome to the Ubuntu Server Installation",
                     align="center")),
            Padding.line_break("")
        ]
        w = (SimpleList(text))
        super().__init__(w)
