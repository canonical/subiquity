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


log = logging.getLogger("subiquity.models.installpath")


class InstallpathModel(object):
    """ Model representing install options

    List of install paths in the form of:
    ('UI Text seen by user', <signal name>, <callback function string>)
    """

    path = None
    packages = {}
    debconf = {}

    @property
    def paths(self):
        return [
            (_('Install Ubuntu'),                 'ubuntu'),
            (_('Install MAAS Region Controller'), 'maas_region'),
            (_('Install MAAS Rack Controller'),   'maas_rack'),
        ]

    def update(self, results):
        if self.path == 'ubuntu':
            self.packages = {}
            self.debconf = {}
        elif self.path == 'maas_region':
            self.packages = {'packages': ['maas']}
            self.debconf['debconf_selections'] = {
                'maas-username': 'maas-region-controller maas/username string %s' % results['username'],
                'maas-password': 'maas-region-controller maas/password password %s' % results['password'],
                }
        elif self.path == 'maas_rack':
            self.packages = {'packages': ['maas-rack-controller']}
            self.debconf['debconf_selections'] = {
                'maas-url': 'maas-rack-controller maas-rack-controller/maas-url string %s' % results['url'],
                'maas-secret': 'maas-rack-controller maas-rack-controller/shared-secret password %s' % results['secret'],
                }
        else:
            raise ValueError("invalid Installpath %s" % self.path)

    def render(self):
        return self.debconf

    def render_cloudinit(self):
        return self.packages
