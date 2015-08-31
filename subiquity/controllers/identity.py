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

from subiquity.controller import ControllerPolicy
from subiquity.models import IdentityModel
from subiquity.ui.views import IdentityView


class IdentityController(ControllerPolicy):
    def __init__(self, common):
        super().__init__(common)
        self.model = IdentityModel()

    def identity(self):
        title = "Profile setup"
        excerpt = ("Input your username and password to log in to the system.")
        footer = ""
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(IdentityView(self.model, self.signal))
