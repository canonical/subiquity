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
import os
import uuid


log = logging.getLogger("subiquity.models.installpath")

SECRET_PATH = '/run/maas.secret'


def maas_prep_secret(secret, confirm=False):
    # Ensure that the file has sensible permissions.
    with open(SECRET_PATH, "w") as secret_f:
        os.fchmod(secret_f.fileno(), 0o640)
    if confirm:
        secret += '\n' + secret
    with open(SECRET_PATH, "w") as secret_f:
        secret_f.write(secret)


class InstallpathModel(object):
    """ Model representing install options

    List of install paths in the form of:
    ('UI Text seen by user', <signal name>, <callback function string>)
    """

    path = None
    source = ''
    cmds = {}

    @property
    def paths(self):
        return [
            (_('Install Ubuntu'),                               'ubuntu'),
            (_('Install Ubuntu with a MAAS Region Controller'), 'maas_region'),
            (_('Install Ubuntu with a MAAS Rack Controller'),   'maas_rack'),
        ]

    def update(self, results):
        if self.path == 'ubuntu':
            self.source = '/media/filesystem'
            self.cmds = {}
        elif self.path == 'maas_region':
            maas_prep_secret(results['secret'], confirm=True)
            user = results['username']
            email = '%s@maas' % user
            self.source = '/media/region'
            self.cmds['late_commands'] = {
                '91-maas': ['sh', '-c', 'curtin in-target -- invoke-rc.d --force postgresql restart || true'],
                '92-maas': ['sh', '-c', 'curtin in-target -- maas-region createadmin --username %s --email %s <%s' % (user, email, SECRET_PATH)],
                '93-maas': ['sh', '-c', 'curtin in-target -- invoke-rc.d --force postgresql stop || true'],
            }
        elif self.path == 'maas_rack':
            maas_prep_secret(results['secret'])
            url = results['url']
            rackuuid = str(uuid.uuid4())
            self.source = '/media/rack'
            self.cmds['late_commands'] = {
                '91-maas': ['curtin', 'in-target', '--', 'maas-rack', 'config', '--uuid', rackuuid, '--region-url', url],
                '92-maas': ['sh', '-c', 'curtin in-target -- maas-rack install-shared-secret <%s' % SECRET_PATH],
            }
        else:
            raise ValueError("invalid Installpath %s" % self.path)

    def render(self):
        return self.cmds
