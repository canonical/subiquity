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

from urwid import WidgetWrap, Pile, Text, ProgressBar
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.ui.lists import SimpleList


class Header(WidgetWrap):
    """ Header Widget

    This widget uses the style key `frame_header`

    :param str title: Title of Header
    :returns: Header()
    """

    def __init__(self, title=None, excerpt=None):
        widgets = [Text("")]
        if title is not None:
            widgets.append(
                Padding.center_79(Color.body(Text(title))))
            widgets.append(Text(""))
        if excerpt is not None:
            widgets.append(
                Padding.center_79(Color.body(Text(excerpt))))
            widgets.append(Text(""))
        super().__init__(Pile(widgets))


class Footer(WidgetWrap):
    """ Footer widget

    Style key: `frame_footer`

    """

    def __init__(self, message="", completion=0):
        message_widget = Padding.center_79(Color.body(Text(message)))
        progress_bar = Padding.center_60(
            ProgressBar(normal='progress_incomplete',
                        complete='progress_complete',
                        current=completion, done=100))
        status = [
            Padding.line_break(""),
            message_widget,
        ]
        if completion > 0:
            status.insert(0, progress_bar)
        super().__init__(Pile(status))


class Body(WidgetWrap):
    """ Body widget
    """

    def __init__(self):
        super().__init__(SimpleList([Text("")]))
