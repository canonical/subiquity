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

from subiquity.controllers.policy import ControllerPolicy
from subiquity.views.welcome import WelcomeView
from subiquity.models.welcome import WelcomeModel
import logging


log = logging.getLogger('subiquity.controllers.welcome')


class WelcomeController(ControllerPolicy):
    """WelcomeController"""
    title = "Wilkommen! Bienvenue! Welcome! Zdrastvutie! Welkom!"
    excerpt = "Please choose your preferred language"
    footer = ("Use UP, DOWN arrow keys, and ENTER, to "
              "select your language.")

    def show(self, *args, **kwds):
        self.ui.set_header(self.title, self.excerpt)
        self.ui.set_footer(self.footer)
        self.ui.set_body(WelcomeView(WelcomeModel, self.finish))
        return

    def finish(self, language=None):
        if language is None:
            raise SystemExit("No language selected, exiting as there are no "
                             "more previous controllers to render.")
        WelcomeModel.selected_language = language
        log.debug("Welcome Model: {}".format(WelcomeModel()))
        return self.ui.next_controller()

__controller_class__ = WelcomeController
