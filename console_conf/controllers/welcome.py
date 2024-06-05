# Copyright 2015 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from console_conf.ui.views import WelcomeView, ChooserWelcomeView

from subiquitycore.controller import BaseController


class WelcomeController(BaseController):

    welcome_view = WelcomeView

    def start_ui(self):
        view = self.welcome_view(self)
        self.ui.set_body(view)

    def done(self):
        self.app.next_screen()

    def cancel(self):
        # Can't go back from here!
        pass


class RecoveryChooserWelcomeController(WelcomeController):

    welcome_view = ChooserWelcomeView

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model
