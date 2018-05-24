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


log = logging.getLogger('subiquity.models.iscsi_disk')


class IscsiDiskModel(object):
    """ Model representing iscsi network disk
    """

    menu = [
        ('Discover volumes now', 'iscsi:discover-volumes'),
        ('Use custom discovery credentials (advanced)',
         'iscsi:custom-discovery-credentials'),
        ('Enter volume details manually', 'iscsi:manual-volume-details')
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

    def get_menu(self):
        return self.menu
