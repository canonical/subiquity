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

import logging
import os

from subiquity.common.keyboard import from_config_file, render
from subiquity.common.types import KeyboardSetting

log = logging.getLogger("subiquity.models.keyboard")


class KeyboardModel:

    def __init__(self, root):
        self.root = root
        config_path = os.path.join(self.root, 'etc', 'default', 'keyboard')
        if os.path.exists(config_path):
            self.setting = from_config_file(config_path)
        else:
            self.setting = KeyboardSetting(layout='us')

    def render(self):
        return {
            'write_files': {
                'etc_default_keyboard': {
                    'path': 'etc/default/keyboard',
                    'content': render(self.setting),
                    'permissions': 0o644,
                    },
                },
            }
