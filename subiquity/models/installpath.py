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


log = logging.getLogger("subiquity.models.installpath")


class InstallpathModel(object):
    """ Model representing install options

    List of install paths in the form of:
    ('UI Text seen by user', <signal name>, <callback function string>)
    """

    path = 'ubuntu'
    # update() is not run, upon selecting the default choice...
    source = '/media/filesystem'
    curtin = {}
    cconfig = {}

    @property
    def paths(self):
        return [
            (_('Install Ubuntu'),                 'ubuntu'),
            (_('Install MAAS Region Controller'), 'maas_region'),
            (_('Install MAAS Rack Controller'),   'maas_rack'),
        ]

    def update(self, results):
        if self.path == 'ubuntu':
            self.source = '/media/filesystem'
            self.curtin = {}
            self.cconfig = {}
        elif self.path == 'maas_region':
            self.source = '/media/region'
            self.curtin['debconf_selections'] = {
                'maas-username': 'maas-region-controller maas/username string %s' % results['username'],
                'maas-password': 'maas-region-controller maas/password password %s' % results['password'],
            }
            self.curtin['late_commands'] = {
                '90-maas': ['rm', '-f', '/target/etc/maas/rackd.conf'],
                '91-maas': ['rm', '-f', '/target/etc/maas/region.conf'],
                '92-maas': ['curtin', 'in-target', '--', 'maas-rack', 'config', '--init'],
                '93-maas': ['curtin', 'in-target', '--', 'dpkg-reconfigure', '-u', '-fnoninteractive', 'maas-rack-controller'],
            }
            # Ideally, we should be creating overlay on top of /media/region
            # starting postgresql server
            # and then executing this in said overlay
            # stopping postgresql server
            # and installing from the touched up overlay
            # as configuring user account needs running postgresql database
            self.cconfig['runcmd'] = [
                "debconf -fnoninteractive -omaas-region-controller /var/lib/dpkg/info/maas-region-controller.config configure",
                "debconf -fnoninteractive -omaas-region-controller /var/lib/dpkg/info/maas-region-controller.postinst configure",
                ]
        elif self.path == 'maas_rack':
            self.source = '/media/rack'
            self.curtin['debconf_selections'] = {
                'maas-url': 'maas-rack-controller maas-rack-controller/maas-url string %s' % results['url'],
                'maas-secret': 'maas-rack-controller maas-rack-controller/shared-secret password %s' % results['secret'],
            }
            self.curtin['late_commands'] = {
                '90-maas': ['rm', '-f', '/target/etc/maas/rackd.conf'],
                '91-maas': ['curtin', 'in-target', '--', 'maas-rack', 'config', '--init'],
                # maas-rack-controller is broken, and does db_input & go on the password question in the postinst...
                # when it should have been done in .config
                # and it doesn't gracefully handle the case of db_go returning 30 skipped
                '93-maas': ['curtin', 'in-target', '--', 'sh', '-c', 'debconf -fnoninteractive -omaas-rack-controller /var/lib/dpkg/info/maas-rack-controller.postinst configure || :'],
            }
            self.cconfig = {}
        else:
            raise ValueError("invalid Installpath %s" % self.path)

    def render(self):
        return self.curtin

    def render_cloudinit(self):
        return self.cconfig
