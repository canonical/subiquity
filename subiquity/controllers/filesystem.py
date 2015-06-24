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
from subiquity.views.filesystem import FilesystemView
from subiquity.models.filesystem import FilesystemModel
import logging

log = logging.getLogger('subiquity.filesystem')


class FilesystemController(ControllerPolicy):
    """ Filesystem Controller """

    title = "Filesystem setup"
    excerpt = ("")

    footer = ("Select available disks to format and mount")

    def show(self, *args, **kwds):
        self.ui.set_header(self.title, self.excerpt)
        self.ui.set_footer(self.footer)
        model = FilesystemModel
        self.ui.set_body(FilesystemView(model, self.finish))
        return

    def finish(self, disk=None):
        if disk is None:
            return self.ui.prev_controller()
        log.info("Filesystem Interface choosen: {}".format(disk))
        return self.ui.exit()

__controller_class__ = FilesystemController
