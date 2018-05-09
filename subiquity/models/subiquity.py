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

from collections import OrderedDict
import os
import uuid
import yaml

from subiquitycore.models.identity import IdentityModel
from subiquitycore.models.network import NetworkModel

from .filesystem import FilesystemModel
from .installpath import InstallpathModel
from .keyboard import KeyboardModel
from .locale import LocaleModel
from .proxy import ProxyModel


def setup_yaml():
    """ http://stackoverflow.com/a/8661021 """
    represent_dict_order = lambda self, data:  self.represent_mapping('tag:yaml.org,2002:map', data.items())
    yaml.add_representer(OrderedDict, represent_dict_order)

setup_yaml()


class SubiquityModel:
    """The overall model for subiquity."""

    def __init__(self, common):
        root = '/'
        if common['opts'].dry_run:
            root = os.path.abspath(".subiquity")
        self.locale = LocaleModel(common['signal'])
        self.keyboard = KeyboardModel(root)
        self.installpath = InstallpathModel()
        self.network = NetworkModel(support_wlan=False)
        self.filesystem = FilesystemModel(common['prober'])
        self.identity = IdentityModel()
        self.proxy = ProxyModel()

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
        if user.ssh_key is not None:
            user_info['ssh_authorized_keys'] = user.ssh_key.splitlines()
        config = {
            'growpart': {
                'mode': 'off',
                },
            'hostname': self.identity.hostname,
            'locale': self.locale.selected_language + '.UTF-8',
            'resize_rootfs': False,
            'users': [user_info],
        }
        return config

    def _cloud_init_files(self):
        # TODO, this should be moved to the in-target cloud-config seed so on first
        # boot of the target, it reconfigures datasource_list to none for subsequent
        # boots.
        # (mwhudson does not entirely know what the above means!)
        userdata = '#cloud-config\n' + yaml.dump(self._cloud_init_config())
        metadata = yaml.dump({'instance-id': str(uuid.uuid4())})
        return [
            ('var/lib/cloud/seed/nocloud-net/meta-data', metadata),
            ('var/lib/cloud/seed/nocloud-net/user-data', userdata),
            ('etc/cloud/ds-identify.cfg', 'policy: enabled\n'),
            ]

    def configure_cloud_init(self, target):
        for path, content in self._cloud_init_files():
            path = os.path.join(target, path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as fp:
                fp.write(content)

    def render(self, target, syslog_identifier):
        config = {
            'install': {
                'target': target,
                'unmount': 'disabled',
                'save_install_config': '/var/log/installer/curtin-install-cfg.yaml',
                'save_install_log': '/var/log/installer/curtin-install.log',
                },

            'sources': {
                'rofs': 'cp://%s' % self.installpath.source,
                },

            'verbosity': 3,

            'partitioning_commands': {
                'builtin': 'curtin block-meta custom',
                },

            'pollinate': {
                'user_agent': {
                    'subiquity': "%s_%s"%(os.environ.get("SNAP_VERSION", 'dry-run'), os.environ.get("SNAP_REVISION", 'dry-run')),
                    },
                },

            'reporting': {
                'subiquity': {
                    'type': 'journald',
                    'identifier': syslog_identifier,
                    },
                },

            'storage': {
                'version': 1,
                'config': self.filesystem.render(),
                },

            'write_files': {
                'etc_default_keyboard': {
                    'path': 'etc/default/keyboard',
                    'content': self.keyboard.setting.render(),
                    },
                },
            }

        if self.proxy.proxy != "":
            config['proxy'] = {
                'http_proxy': self.proxy.proxy,
                'https_proxy': self.proxy.proxy,
                }

        if not self.filesystem.add_swapfile():
            config['swap'] = {'size': 0}

        config.update(self.network.render())
        config.update(self.installpath.render())

        return config
