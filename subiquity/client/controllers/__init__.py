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

from subiquitycore.tuicontroller import RepeatedController
from .drivers import DriversController
from .filesystem import FilesystemController
from .identity import IdentityController
from .keyboard import KeyboardController
from .mirror import MirrorController
from .network import NetworkController
from .progress import ProgressController
from .proxy import ProxyController
from .refresh import RefreshController
from .serial import SerialController
from .snaplist import SnapListController
from .source import SourceController
from .ssh import SSHController
from .ubuntu_advantage import UbuntuAdvantageController
from .welcome import WelcomeController
from .zdev import ZdevController

# see SubiquityClient.controllers for another list
__all__ = [
    'DriversController',
    'FilesystemController',
    'IdentityController',
    'KeyboardController',
    'MirrorController',
    'NetworkController',
    'ProgressController',
    'ProxyController',
    'RefreshController',
    'RepeatedController',
    'SerialController',
    'SnapListController',
    'SourceController',
    'SSHController',
    'UbuntuAdvantageController',
    'WelcomeController',
    'ZdevController',
]
