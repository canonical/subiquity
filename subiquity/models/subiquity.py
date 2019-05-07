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
import logging
import os
import sys
import uuid
import yaml

from curtin.config import merge_config

from subiquitycore.models.identity import IdentityModel
from subiquitycore.models.network import NetworkModel
from subiquitycore.file_util import write_file
from subiquitycore.utils import run_command

from .filesystem import FilesystemModel
from .installpath import InstallpathModel
from .keyboard import KeyboardModel
from .locale import LocaleModel
from .proxy import ProxyModel
from .mirror import MirrorModel
from .snaplist import SnapListModel
from .ssh import SSHModel


log = logging.getLogger('subiquity.models.subiquity')


def setup_yaml():
    """ http://stackoverflow.com/a/8661021 """
    represent_dict_order = (
        lambda self, data: self.represent_mapping('tag:yaml.org,2002:map',
                                                  data.items()))
    yaml.add_representer(OrderedDict, represent_dict_order)


setup_yaml()

HOSTS_CONTENT = """\
127.0.0.1 localhost
127.0.1.1 {hostname}

# The following lines are desirable for IPv6 capable hosts
::1     ip6-localhost ip6-loopback
fe00::0 ip6-localnet
ff00::0 ip6-mcastprefix
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
"""


class SubiquityModel:
    """The overall model for subiquity."""

    target = '/target'

    def __init__(self, common):
        self.root = '/'
        self.opts = common['opts']
        if self.opts.dry_run:
            self.root = os.path.abspath(".subiquity")
            self.target = self.root

        self.locale = LocaleModel(common['signal'])
        self.keyboard = KeyboardModel(self.root)
        self.installpath = InstallpathModel(
            target=self.target,
            sources=common['opts'].sources)
        self.network = NetworkModel(support_wlan=False)
        self.proxy = ProxyModel()
        self.mirror = MirrorModel()
        self.filesystem = FilesystemModel()

        # Collect the models that produce data for the curtin config.
        self._install_models = [
            self.keyboard,
            self.installpath,
            self.network,
            self.proxy,
            self.mirror,
            self.filesystem,
            ]

        self.identity = IdentityModel()
        self.ssh = SSHModel()
        self.snaplist = SnapListModel()

    def get_target_groups(self):
        command = ['chroot', self.target, 'getent', 'group']
        if self.opts.dry_run:
            del command[:2]
        cp = run_command(command, check=True)
        groups = set()
        for line in cp.stdout.splitlines():
            groups.add(line.split(':')[0])
        return groups

    def _cloud_init_config(self):
        user = self.identity.user
        users_and_groups_path = (
            os.path.join(os.environ.get("SNAP", "."),
                         "users-and-groups"))
        if os.path.exists(users_and_groups_path):
            groups = open(users_and_groups_path).read().split()
        else:
            groups = ['admin']
        groups.append('sudo')
        groups = [group for group in groups
                  if group in self.get_target_groups()]
        user_info = {
            'name': user.username,
            'gecos': user.realname,
            'passwd': user.password,
            'shell': '/bin/bash',
            'groups': groups,
            'lock-passwd': False,
            }
        if self.ssh.authorized_keys:
            user_info['ssh_authorized_keys'] = self.ssh.authorized_keys
        config = {
            'growpart': {
                'mode': 'off',
                },
            'locale': self.locale.selected_language + '.UTF-8',
            'preserve_hostname': True,
            'resize_rootfs': False,
            'users': [user_info],
        }
        if self.ssh.install_server:
            config['ssh_pwauth'] = self.ssh.pwauth
        if self.snaplist.to_install:
            cmds = []
            for snap_name, selection in sorted(
                    self.snaplist.to_install.items()):
                cmd = ['snap', 'install', '--channel=' + selection.channel]
                if selection.is_classic:
                    cmd.append('--classic')
                cmd.append(snap_name)
                cmds.append(' '.join(cmd))
            config['snap'] = {
                'commands': cmds,
                }
        return config

    def _cloud_init_files(self):
        # TODO, this should be moved to the in-target cloud-config seed so on
        # first boot of the target, it reconfigures datasource_list to none
        # for subsequent boots.
        # (mwhudson does not entirely know what the above means!)
        userdata = '#cloud-config\n' + yaml.dump(self._cloud_init_config())
        metadata = yaml.dump({'instance-id': str(uuid.uuid4())})
        hostname = self.identity.hostname.strip()
        return [
            ('var/lib/cloud/seed/nocloud-net/meta-data', metadata, 0o644),
            ('var/lib/cloud/seed/nocloud-net/user-data', userdata, 0o600),
            ('etc/cloud/ds-identify.cfg', 'policy: enabled\n', 0o644),
            ('etc/hostname', hostname + "\n", 0o644),
            ('etc/hosts', HOSTS_CONTENT.format(hostname=hostname), 0o644),
            ]

    def configure_cloud_init(self):
        for path, content, mode in self._cloud_init_files():
            path = os.path.join(self.target, path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            write_file(path, content, mode, omode="w")

    def _media_info(self):
        if os.path.exists('/cdrom/.disk/info'):
            with open('/cdrom/.disk/info') as fp:
                return fp.read()
        else:
            return "media-info"

    def render(self, syslog_identifier):
        config = {
            'apt': {
                'preserve_sources_list': False,
                },

            'curthooks_commands': {
                '000-configure-run': [
                    '/snap/bin/subiquity.subiquity-configure-run',
                    ],
                '001-configure-apt': [
                    '/snap/bin/subiquity.subiquity-configure-apt',
                    sys.executable, str(self.network.has_network).lower(),
                    ],
                },

            'install': {
                'target': self.target,
                'unmount': 'disabled',
                'save_install_config':
                    '/var/log/installer/curtin-install-cfg.yaml',
                'save_install_log':
                    '/var/log/installer/curtin-install.log',
                },

            'verbosity': 3,

            'pollinate': {
                'user_agent': {
                    'subiquity': "%s_%s" % (os.environ.get("SNAP_VERSION",
                                                           'dry-run'),
                                            os.environ.get("SNAP_REVISION",
                                                           'dry-run')),
                    },
                },

            'reporting': {
                'subiquity': {
                    'type': 'journald',
                    'identifier': syslog_identifier,
                    },
                },

            'write_files': {
                'etc_machine_id': {
                    'path': 'etc/machine-id',
                    'content': open('/etc/machine-id').read(),
                    'permissions': 0o444,
                    },
                'media_info': {
                    'path': 'var/log/installer/media-info',
                    'content': self._media_info(),
                    'permissions': 0o644,
                    },
                },
            }

        for model in self._install_models:
            log.debug("merging config from %s", model)
            merge_config(config, model.render())

        mp_file = os.path.join(self.root, "run/kernel-meta-package")
        if os.path.exists(mp_file):
            with open(mp_file) as fp:
                kernel_package = fp.read().strip()
            config['kernel'] = {
                'package': kernel_package,
                }

        return config
