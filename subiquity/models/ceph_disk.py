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

from subiquity.model import ModelPolicy


log = logging.getLogger('subiquity.models.ceph_disk')


class CephDiskModel(ModelPolicy):
    """ Model representing iscsi Ceph storage
    """
    prev_signal = (
        'Back to filesystem view',
        'filesystem:show',
        'filesystem'
    )

    signals = [
        ('Ceph view',
         'ceph:show',
         'ceph'),
        ('Ceph finish',
         'ceph:finish',
         'ceph_handler')
    ]

    menu = [
        ('Fetch key from USB',
         'ceph:fetch-key-usb',
         'fetch_key_usb'),
        ('Fetch key by SSH (scp)',
         'ceph:fetch-key-ssh',
         'fetch_key_ssh')
    ]

    server_authentication = {
        'mon': None,
        'username': None,
        'key': None
    }

    def get_signal_by_name(self, selection):
        for x, y, z in self.get_signals():
            if x == selection:
                return y

    def get_signals(self):
        return self.signals + self.menu

    def get_menu(self):
        return self.menu
