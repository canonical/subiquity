# Copyright 2018 Canonical, Ltd.
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

from subiquitycore.controller import BaseController

from subiquity.ui.views.snaplist import SnapListView

log = logging.getLogger('subiquity.controllers.snaplist')


class SnapListController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.snaplist

    def default(self):
        self.ui.set_header(
            _("Featured Server Snaps"),
            _("These are popular snaps in server environments. Select or deselect with SPACE, press ENTER to see more details of the package, publisher and versions available."),
            )
        self.ui.set_body(SnapListView(self.model, self))

    def done(self, snaps_to_install):
        self.signal.emit_signal("next-screen")

    def cancel(self, sender=None):
        self.signal.emit_signal("prev-screen")
