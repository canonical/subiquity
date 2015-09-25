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
                   Pile)
from subiquity.view import ViewPolicy
from subiquity.ui.utils import Padding

log = logging.getLogger("subiquity.ui.views.installprogress")


class ProgressView(ViewPolicy):
    def __init__(self, signal):
        """
        :param output_w: Filler widget to display updated status text
        """
        self.signal = signal
        self.text = Text("Wait for it ...")
        self.body = [
            Padding.center_79(self.text)
        ]
        super().__init__(Filler(Pile(self.body), valign="middle"))
