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

from subiquity.controller import SubiquityController


class PackageController(SubiquityController):

    model_name = autoinstall_key = "packages"
    autoinstall_default = []
    autoinstall_schema = {
        'type': 'array',
        'items': {'type': 'string'},
        }

    def load_autoinstall_data(self, data):
        self.model[:] = data

    def make_autoinstall(self):
        return self.model
