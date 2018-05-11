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

from subiquitycore.controllers.login import LoginController  # NOQA
from subiquitycore.controllers.network import NetworkController  # NOQA

from .identity import IdentityController  # NOQA
from .installpath import InstallpathController  # NOQA
from .installprogress import InstallProgressController  # NOQA
from .filesystem import FilesystemController  # NOQA
from .keyboard import KeyboardController  # NOQA
from .proxy import ProxyController  # NOQA
from .snaplist import SnapListController
from .welcome import WelcomeController  # NOQA
