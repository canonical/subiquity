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
    Text,
    ProgressBar,
    )
from subiquitycore.ui.container import (
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.utils import Padding, Color


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


class Footer(WidgetWrap):
    """ Footer widget

    Style key: `frame_footer`

    """

    def __init__(self, message, current, complete):
        if isinstance(message, str):
            message = Text(message)
        message = Padding.center_79(message, min_width=76)
        progress_bar = Padding.center_60(
            StepsProgressBar(normal='progress_incomplete',
                             complete='progress_complete',
                             current=current, done=complete))
        status = [
            progress_bar,
            Padding.line_break(""),
            message,
        ]
        super().__init__(Color.frame_footer(Pile(status)))
