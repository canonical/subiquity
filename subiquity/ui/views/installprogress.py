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
from urwid import (Text, Filler,
                   ListBox, BoxAdapter)
from subiquity.view import ViewPolicy
from subiquity.ui.utils import Color, Padding

log = logging.getLogger("subiquity.ui.views.installprogress")


class ProgressOutput(ViewPolicy):
    def __init__(self, signal, txt):
        self.signal = signal
        self.txt = Text(txt)
        flr = Filler(Color.info_minor(self.txt),
                     valign="top")
        super().__init__(BoxAdapter(flr, height=20))

    def set_text(self, data):
        self.txt.set_text(data)


class ProgressView(ViewPolicy):
    def __init__(self, signal, output_w):
        """
        :param output_w: Filler widget to display updated status text
        """
        self.signal = signal
        self.body = [
            Padding.center_79(output_w)
        ]
        super().__init__(ListBox(self.body))
