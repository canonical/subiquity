# Copyright 2020 Canonical, Ltd.
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

from console_conf.ui.views import ChooserView, ChooserConfirmView

from subiquitycore.controller import BaseController

log = logging.getLogger("console_conf.controllers.chooser")


class RecoveryChooserBaseController(BaseController):
    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model

    def cancel(self):
        # exit without taking any action
        self.app.exit()


class RecoveryChooserController(RecoveryChooserBaseController):
    def start_ui(self):
        view = ChooserView(self, self.model.systems)
        self.ui.set_body(view)

    def select(self, system, action):
        self.model.select(system, action)
        self.app.next_screen()


class RecoveryChooserConfirmController(RecoveryChooserBaseController):
    def start_ui(self):
        view = ChooserConfirmView(self, self.model.selection)
        self.ui.set_body(view)

    def confirm(self):
        log.warning("user action %s", self.model.selection)
        # output the choice
        self.app.respond(self.model.selection)
        self.app.exit()
