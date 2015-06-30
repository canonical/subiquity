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
from subiquity.views.installpath import InstallpathView
from subiquity.models.installpath import InstallpathModel
import logging
import subprocess

log = logging.getLogger('subiquity.installpath')


class InstallpathController(ControllerPolicy):
    """InstallpathController"""

    title = "15.10"
    excerpt = ("Welcome to Ubuntu! The world's favourite platform "
               "for clouds, clusters and amazing internet things. "
               "This is the installer for Ubuntu on servers and "
               "internet devices.")
    footer = ("Use UP, DOWN arrow keys, and ENTER, to "
              "navigate options")

    def show(self, *args, **kwds):
        log.debug("Loading install path controller")
        self.ui.set_header(self.title, self.excerpt)
        self.ui.set_footer(self.footer)
        model = InstallpathModel()
        self.ui.set_body(InstallpathView(model, self.finish))
        return

    def finish(self, install_selection=None):
        if install_selection is None:
            return self.ui.prev_controller()
        # subprocess.check_call("/usr/local/bin/curtin_wrap.sh")
        return self.ui.next_controller()

__controller_class__ = InstallpathController
