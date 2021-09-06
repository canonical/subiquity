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
from system_setup.models.system_setup import SystemSetupModel
from subiquity.models.subiquity import ModelNames

import os


INSTALL_MODEL_NAMES = ModelNames({
        "locale",
        "wslconfbase",
    },
    wsl_setup={
        "identity",
    },
    wsl_configuration={
        "wslconfadvanced",
    })

POSTINSTALL_MODEL_NAMES = ModelNames(set())


class SystemSetupServer(SubiquityServer):

    from system_setup.server import controllers as controllers_mod
    controllers = [
        "Reporting",
        "Error",
        "Locale",
        "Identity",
        "WSLConfigurationBase",
        "WSLConfigurationAdvanced",
        "Configure",
        "Late",
        "SetupShutdown",
    ]

    supported_variants = ["wsl_setup", "wsl_configuration"]

    def make_model(self):
        root = '/'
        if self.opts.dry_run:
            root = os.path.abspath('.subiquity')
        return SystemSetupModel(root, INSTALL_MODEL_NAMES,
                                POSTINSTALL_MODEL_NAMES)
