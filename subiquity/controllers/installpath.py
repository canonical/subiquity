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

from subiquity.controllers import BaseController
from subiquity.views.installpath import InstallpathView
from subiquity.models.installpath import InstallpathModel


class InstallpathController(BaseController):
    """InstallpathController"""
    controller_name = "Installation path controller"

    def show(self, *args, **kwds):
        model = InstallpathModel()
        return InstallpathView(model, self.finish)

    def finish(self, install_selection=None):
        if install_selection is None:
            self.prev_controller("WelcomeController")
        else:
            raise SystemExit("Install selection: {}".format(install_selection))

__controller_class__ = InstallpathController
