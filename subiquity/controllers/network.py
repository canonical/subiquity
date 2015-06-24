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
from subiquity.views.network import NetworkView
from subiquity.models.network import NetworkModel
import logging

log = logging.getLogger('subiquity.network')


class NetworkController(ControllerPolicy):
    """InstallpathController"""

    title = "Network connections"
    excerpt = ("Configure at least the main interface this server will "
               "use to talk to other machines, and preferably provide "
               "sufficient access for updates.")

    footer = ("Additional networking info here")

    def show(self, *args, **kwds):
        self.ui.set_header(self.title, self.excerpt)
        self.ui.set_footer(self.footer)
        model = NetworkModel
        self.ui.set_body(NetworkView(model, self.finish))
        return

    def finish(self, interface=None):
        if interface is None:
            return self.ui.prev_controller()
        log.info("Network Interface choosen: {}".format(interface))
        return self.ui.next_controller()

__controller_class__ = NetworkController
