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

from subiquitycore.ui.buttons import ok_btn
from subiquitycore.ui.frame import SubiquityCoreUI


log = logging.getLogger('subiquity.ui.frame')


class SubiquityUI(SubiquityCoreUI):

    def __init__(self, app):
        self.right_icon = ok_btn(
            _("More..."), on_press=lambda sender: app.show_global_extra())
        self.right_icon.attr_map = {}
        super().__init__()
