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
    Text,
    ProgressBar,
    )

from subiquitycore.ui.container import (
    Columns,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.ui.width import widget_width

log = logging.getLogger('subiquitycore.ui.anchors')


class Header(WidgetWrap):
    """ Header Widget

    This widget uses the style key `frame_header`

    :param str title: Title of Header
    :returns: Header()
    """

    def __init__(self, title):
        if isinstance(title, str):
            title = Text(title)
        title = Padding.center_79(title, min_width=76)
        super().__init__(Color.frame_header(
                Pile(
                    [Text(""), title, Text("")])))


class StepsProgressBar(ProgressBar):

    def get_text(self):
        return "{} / {}".format(self.current, self.done)


class MyColumns(Columns):
    # The idea is to render output like this:
    #
    #                  message                [ help  ]
    # [ lpad        ][ middle        ][ rpad ][ right ]
    #
    # The constraints are:
    #
    # 1. lpad + rpad + right + message = maxcol
    #
    # 2. lpad and rpad are at least 1
    #
    # 3. right is fixed
    #
    # 4. if possible, lpad = rpad + right and middle is 79% of maxcol
    #    or 76, whichever is greater.

    def column_widths(self, size, focus=False):
        maxcol = size[0]
        right = widget_width(self.contents[3][0])

        center = max(79*maxcol//100, 76)
        lpad = (maxcol - center)//2
        rpad = lpad - right
        if rpad < 1:
            rpad = 1
        middle = maxcol - (lpad + rpad + right)
        return [lpad, middle, rpad, right]


class Footer(WidgetWrap):
    """ Footer widget

    Style key: `frame_footer`

    """

    def __init__(self, message, right_icon, current, complete):
        if isinstance(message, str):
            message = Text(message)
        progress_bar = Padding.center_60(
            StepsProgressBar(normal='progress_incomplete',
                             complete='progress_complete',
                             current=current, done=complete))
        status = [
            progress_bar,
            Padding.line_break(""),
            MyColumns([Text(""), message, Text(""), right_icon]),
        ]
        super().__init__(Color.frame_footer(Pile(status)))
