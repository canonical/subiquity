# Copyright 2021 Canonical, Ltd.
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


from subiquity.client.controllers import WelcomeController

from .identity import WSLIdentityController
from .summary import SummaryController
from .wslconfadvanced import WSLConfigurationAdvancedController
from .wslconfbase import WSLConfigurationBaseController
from .wslsetupoptions import WSLSetupOptionsController

__all__ = [
    "WelcomeController",
    "WSLSetupOptionsController",
    "WSLIdentityController",
    "WSLConfigurationBaseController",
    "WSLConfigurationAdvancedController",
    "SummaryController",
]
