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

from subiquity.server.controller import NonInteractiveController


class UserdataController(NonInteractiveController):

    model_name = 'userdata'
    autoinstall_key = "user-data"
    autoinstall_default = {}
    autoinstall_schema = {
        'type': 'object',
        }

    def load_autoinstall_data(self, data):
        self.model.clear()
        self.model.update(data)

    def make_autoinstall(self):
        return self.app.base_model.userdata
