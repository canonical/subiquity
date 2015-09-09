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
from collections import OrderedDict
from subiquity.model import ModelPolicy


log = logging.getLogger('subiquity.models.raid')


class RaidModel(ModelPolicy):
    """ Model representing software raid
    """
    prev_signal = (
        'Back to filesystem view',
        'filesystem:show',
        'filesystem'
    )

    signals = [
        ('Create software RAID',
         'raid:show',
         'raid'),
        ('Finish software RAID',
         'raid:finish',
         'raid_handler')
    ]

    menu = [
        ('RAID Level',
         'raid:set-raid-level',
         'set_raid_level'),
        ('Hot spares',
         'raid:set-hot-spares',
         'set_hot_spares'),
        ('Chunk size',
         'raid:set-chunk-size',
         'set_chunk_size')
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

    def get_signal_by_name(self, selection):
        for x, y, z in self.get_signals():
            if x == selection:
                return y

    def get_signals(self):
        return self.signals

    def get_menu(self):
        return self.menu
