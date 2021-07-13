# Copyright 2021 Canonical, Ltd.
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

from subiquity.server.server import SubiquityServer
from system_setup.models.system_server import SystemSetupModel
import os


class SystemSetupServer(SubiquityServer):

    from system_setup.server import controllers as controllers_mod
    controllers = [
        "Reporting",
        "Error",
        "Userdata",
        "Locale",
        "Identity",
        "WSLConfiguration1",
        "WSLConfiguration2"
        ]

    def make_model(self):
        root = '/'
        if self.opts.dry_run:
            root = os.path.abspath('.subiquity')
        return SystemSetupModel(root)
