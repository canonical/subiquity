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


log = logging.getLogger('subiquity.models.iscsi_disk')


class IscsiDiskModel(BaseModel):
    """ Model representing iscsi network disk
    """
    prev_signal = (
        'Back to filesystem view',
        'filesystem:show',
        'filesystem'
    )

    signals = [
        ('iSCSI view',
         'iscsi:show',
         'iscsi'),
        ('iSCSI finish',
         'iscsi:finish',
         'iscsi_handler')
    ]

    menu = [
        ('Discover volumes now',
         'iscsi:discover-volumes',
         'discover_volumes'),
        ('Use custom discovery credentials (advanced)',
         'iscsi:custom-discovery-credentials',
         'custom_discovery_credentials'),
        ('Enter volume details manually',
         'iscsi:manual-volume-details',
         'manual_volume_details')
    ]

    server_authentication = {
        'server_host': None,
        'anonymous': False,
        'username': None,
        'password': None,
        'server_auth': False,
        'server_username': None,
        'server_password': None
    }

    def get_signal_by_name(self, selection):
        for x, y, z in self.get_signals():
            if x == selection:
                return y

    def get_signals(self):
        return self.signals + self.menu

    def get_menu(self):
        return self.menu
