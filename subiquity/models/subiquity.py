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

import os
import uuid
import yaml

from subiquitycore.models.identity import IdentityModel
from subiquitycore.models.network import NetworkModel

from .filesystem import FilesystemModel
from .keyboard import KeyboardModel
from .locale import LocaleModel


class SubiquityModel:
    """The overall model for subiquity."""

    def __init__(self, common):
        self.locale = LocaleModel()
        self.keyboard = KeyboardModel()
        self.network = NetworkModel()
        self.filesystem = FilesystemModel(common['prober'])
        self.identity = IdentityModel()

    def _cloud_init_config(self):
        user = self.identity.user
        users_and_groups_path = os.path.join(os.environ.get("SNAP", "/does-not-exist"), "users-and-groups")
        if os.path.exists(users_and_groups_path):
            groups = open(users_and_groups_path).read().split()
        else:
            groups = ['admin']
        groups.append('sudo')
        user_info = {
            'name': user.username,
            'gecos': user.realname,
            'passwd': user.password,
            'shell': '/bin/bash',
            'groups': groups,
            'lock-passwd': False,
            }
        if user.ssh_import_id is not None:
            user_info['ssh_import_id'] = [user.ssh_import_id]
        # XXX this should set up the locale too.
        return {
            'users': [user_info],
            'hostname': self.identity.hostname,
        }

    def _write_files_config(self):
        # TODO, this should be moved to the in-target cloud-config seed so on first
        # boot of the target, it reconfigures datasource_list to none for subsequent
        # boots.
        # (mwhudson does not entirely know what the above means!)
        userdata = '#cloud-config\n' + yaml.dump(self._cloud_init_config())
        metadata = yaml.dump({'instance-id': str(uuid.uuid4())})
        return {
            'postinst_metadata': {
                'path': 'var/lib/cloud/seed/nocloud-net/meta-data',
                'content': metadata,
                },
            'postinst_userdata': {
                'path': 'var/lib/cloud/seed/nocloud-net/user-data',
                'content': userdata,
                },
            'postinst_enable_cloudinit': {
                'path': 'etc/cloud/ds-identify.cfg',
                'content': 'policy: enabled\n',
                },
            }

    def render(self, install_step, reporting_url=None):
        disk_actions = self.filesystem.render()
        if install_step == "postinstall":
            for a in disk_actions:
                a['preserve'] = True
        config = {
            'partitioning_commands': {
                'builtin': 'curtin block-meta custom',
                },

            'reporting': {
                'subiquity': {
                    'type': 'print',
                    },
                },

            'storage': {
                'version': 1,
                'config': disk_actions,
                },
            }
        if install_step == "install":
            config.update(self.network.render())
        else:
            config['write_files'] = self._write_files_config()

        if reporting_url is not None:
            config['reporting']['subiquity'] = {
                'type': 'webhook',
                'endpoint': reporting_url,
                }
        return config
