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


from .identity import WSLIdentityController
from .integration import IntegrationController
from .overview import OverviewController
from .reconfiguration import ReconfigurationController

from subiquity.client.controllers import (ProgressController,
                                          WelcomeController)


__all__ = [
    'WelcomeController',
    'WSLIdentityController',
    'ProgressController',
    'IntegrationController',
    'OverviewController',
    'ReconfigurationController',
]
