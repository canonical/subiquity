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


from console_conf.ui.views import WelcomeView
from subiquitycore.models import WelcomeModel
from subiquitycore.controllers.welcome import WelcomeController as WelcomeControllerBase


class WelcomeController(WelcomeControllerBase):
    def welcome(self):
        title = "                            Welcome!"
        excerpt = "Please choose your preferred language"
        footer = ("Use UP, DOWN arrow keys, and ENTER, to "
                  "select your language.")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        view = WelcomeView(self.model, self.signal)
        self.ui.set_body(view)
