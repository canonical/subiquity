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
from subiquitycore.model import BaseModel


log = logging.getLogger('subiquity.models.raid')


class RaidModel(BaseModel):
    """ Model representing software raid
    """

    menu = [
        ('RAID Level', 'raid:set-raid-level'),
        ('Hot spares', 'raid:set-hot-spares'),
        ('Chunk size', 'raid:set-chunk-size')
    ]

    raid_levels = ['0', '1', '5', '6', '10', 'linear']

    raid_levels_map = {
        'linear': {'min_disks': 0},
        '0': {'min_disks': 0},
        '1': {'min_disks': 0},
        '5': {'min_disks': 0},
        '6': {'min_disks': 0},
        '10': {'min_disks': 0}
    }

    def get_menu(self):
        return self.menu
