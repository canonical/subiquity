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
    int_scale,
    SolidFill,
    Text,
    )

from subiquitycore.ui.container import (
    Columns,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.utils import Color
from subiquitycore.ui.width import widget_width

log = logging.getLogger('subiquitycore.ui.anchors')


class HeaderColumns(Columns):
    # The idea is to render output like this:
    #
    # [ pad ][ message       ][ btn ][ pad ]
    #
    # The constraints are:
    #
    # 1. pad + message + btn + pad = maxcol
    #
    # 2. pad is at least 1
    #
    # 3. btn is fixed
    #
    # 4. message + btn is 79% of maxcol or 76, whichever is greater.

    def column_widths(self, size, focus=False):
        maxcol = size[0]
        btn = widget_width(self.contents[2][0])

        center = max(int_scale(79, 101, maxcol + 1), 76)
        message = center - btn
        pad = (maxcol - center)//2
        if pad <= 0:
            pad = 1
            message = maxcol - 2 - btn
        return [pad, message, btn, pad]


class Header(WidgetWrap):
    """ Header Widget """

    def __init__(self, title, right_icon):
        if isinstance(title, str):
            title = Text(title)
        title = HeaderColumns([
            Text(""),
            title,
            right_icon,
            Text(""),
            ])
        super().__init__(
                Pile([
                    (1, Color.frame_header_fringe(
                        SolidFill("\N{lower half block}"))),
                    Color.frame_header(title),
                    (1, Color.frame_header_fringe(
                        SolidFill("\N{upper half block}"))),
                    ]))
