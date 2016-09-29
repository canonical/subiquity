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

import logging

from subiquitycore.controller import BaseController

from subiquity.models import RaidDiskModel

log = logging.getLogger("subiquitycore.controller.raid")


class RaidDiskController(BaseController):
    signals = [
        ('menu:raid:main',      'raid'),
        ('raid:finish',         'raid_handler'),
        ('raid:set-raid-level', 'set_raid_level'),
        ('raid:set-hot-spares', 'set_hot_spares'),
        ('raid:set-chunk-size', 'set_chunk_size'),
    ]

    def __init__(self, common):
        super().__init__(common)
        self.model = RaidDiskModel()

    def raid(self):
        pass

    def raid_handler(self):
        pass
