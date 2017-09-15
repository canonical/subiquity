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

from urwid import (
    Filler,
    ProgressBar,
    Text,
    WidgetWrap,
    )

from subiquitycore.ui.container import Columns, Pile
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
                Padding.center_79(Text(title)))
            widgets.append(Text(""))
        w = Color.frame_header(Pile(widgets))
        if excerpt is not None:
            widgets = [
                Text(""),
                Padding.center_79(Text(excerpt)),
                Text(""),
            ]
        else:
            widgets = [Text("")]
        w = Pile([w] + widgets)
        super().__init__(w)



#
#   +--------+     [ progress bar     ]   +----------+
#   | BACK   |                            | CONTINUE |
#   +--------+          message           +----------+
#

# Pile([
#   Text(""),
#   Columns([
#     (fixed, 1, Text("")),
#     (fixed, 10, Button(left)),
#     Pile([
#       ProgressBar,
#       Text(""),
#       Text(message),])
#     (fixed, 10, Button(right)),
#     (fixed, 1, Text("")),
#     ], dividechars=1)
#   Text(""),
#   ])

class Footer(WidgetWrap):
    """ Footer widget

    Style key: `frame_footer`

    """

    def __init__(self, message="", completion=0, leftbutton=None, rightbutton=None):
        message_widget = Text(message)
        progress_bar = Padding.center_80(
            ProgressBar(normal='progress_incomplete',
                        complete='progress_complete',
                        current=completion, done=100))
        if leftbutton is None:
            leftbutton = Text("")
        if rightbutton is None:
            rightbutton = Text("")
        super().__init__(Color.frame_footer(Pile([
            Text(""),
            Columns([
                (1, Text("")),
                (12, leftbutton),
                Pile([
                    progress_bar,
                    (2, Filler(message_widget, valign='bottom')),
                    ]),
                (12, rightbutton),
                (1, Text("")),
                ], dividechars=1),
            Text(""),
            ])))


class Body(WidgetWrap):
    """ Body widget
    """

    def __init__(self):
        super().__init__(SimpleList([Text("")]))
