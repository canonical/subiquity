# Copyright 2019 Canonical, Ltd.
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
    PopUpLauncher,
    )

from subiquitycore.ui.buttons import (
    header_btn,
    )


log = logging.getLogger('subiquity.ui.help')


class HelpButton(PopUpLauncher):

    def __init__(self, app):
        self.app = app
        super().__init__(header_btn(_("Help")))
