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

from subiquitycore.models.identity import IdentityModel
from subiquitycore.models.network import NetworkModel

from .filesystem import FilesystemModel
from .locale import LocaleModel


class SubiquityModel:
    """The overall model for subiquity."""

    def __init__(self, common):
        self.locale = LocaleModel()
        self.network = NetworkModel()
        self.filesystem = FilesystemModel(common['prober'])
        self.identity = IdentityModel()
