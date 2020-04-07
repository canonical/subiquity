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

from console_conf.ui.views import (
    ChooserView,
    ChooserCurrentSystemView,
    ChooserConfirmView,
    )

from subiquitycore.controller import BaseController

log = logging.getLogger("console_conf.controllers.chooser")


class RecoveryChooserBaseController(BaseController):

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model

    def cancel(self):
        # exit without taking any action
        self.app.exit()

    def back(self):
        self.app.prev_sceen()


class RecoveryChooserController(RecoveryChooserBaseController):

    def __init__(self, app):
        super().__init__(app)
        self._model_view, self._all_view = self._make_views()
        # one of the current views
        self._current_view = None

    def start_ui(self):
        # current view is preserved, so going back comes back to the right
        # screen
        if self._current_view is None:
            # right off the start, default to all-systems view
            self._current_view = self._all_view
            # unless we can show the current model
            if self._model_view is not None:
                self._current_view = self._model_view

        self.ui.set_body(self._current_view)

    def _make_views(self):
        current_view = None
        if self.model.current and self.model.current.actions:
            # only when we have a current system and it has actions available
            more = len(self.model.systems) > 1
            current_view = ChooserCurrentSystemView(self,
                                                    self.model.current,
                                                    has_more=more)

        all_view = ChooserView(self, self.model.systems)
        return current_view, all_view

    def select(self, system, action):
        self.model.select(system, action)
        self.app.next_screen()

    def more_options(self):
        self._current_view = self._all_view
        self.ui.set_body(self._all_view)

    def back(self):
        if self._current_view == self._all_view and \
           self._model_view is not None:
            # back in the all-systems screen goes back to the current model
            # screen, provided we have one
            self._current_view = self._model_view
            self.ui.set_body(self._current_view)


class RecoveryChooserConfirmController(RecoveryChooserBaseController):
    def start_ui(self):
        view = ChooserConfirmView(self, self.model.selection)
        self.ui.set_body(view)

    def confirm(self):
        log.warning("user action %s", self.model.selection)
        # output the choice
        self.app.respond(self.model.selection)
        self.app.exit()

    def back(self):
        self.model.unselect()
        self.app.prev_screen()
