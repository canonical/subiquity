# Copyright 2018 Canonical, Ltd.
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

import logging
from typing import List

log = logging.getLogger("subiquity.models.ssh")


class SSHModel:

    def __init__(self):
        self.install_server = False
        self.authorized_keys: List[str] = []
        self.pwauth = True
        # Although the generated config just contains the key above,
        # we store the imported id so that we can re-fill the form if
        # we go back to it.
        self.ssh_import_id = ''

    async def target_packages(self):
        if self.install_server:
            return ['openssh-server']
        else:
            return []
