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

import asyncio
import copy
from collections import OrderedDict
import logging
import os
import sys
import uuid
import yaml

from curtin.commands.install import CONFIG_BUILTIN
from curtin.config import merge_config

from subiquitycore.file_util import write_file
from subiquitycore.utils import run_command

from .filesystem import FilesystemModel
from .keyboard import KeyboardModel
from .locale import LocaleModel
from .proxy import ProxyModel
from .mirror import MirrorModel
from .network import NetworkModel
from .snaplist import SnapListModel
from .ssh import SSHModel
from .identity import IdentityModel


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

# Models that contribute to the curtin config
INSTALL_MODEL_NAMES = [
    "debconf_selections",
    "filesystem",
    "keyboard",
    "mirror",
    "network",
    "proxy",
    ]

# Models that contribute to the cloud-init config (and other postinstall steps)
POSTINSTALL_MODEL_NAMES = [
    "identity",
    "locale",
    "packages",
    "snaplist",
    "ssh",
    "userdata",
    ]

ALL_MODEL_NAMES = INSTALL_MODEL_NAMES + POSTINSTALL_MODEL_NAMES


class DebconfSelectionsModel:

    def __init__(self):
        self.selections = ''

    def render(self):
        return {'debconf_selections': {'subiquity': self.selections}}


class SubiquityModel:
    """The overall model for subiquity."""

    target = '/target'

    def __init__(self, root, sources=()):
        self.root = root
        if root != '/':
            self.target = root

        self.debconf_selections = DebconfSelectionsModel()
        self.filesystem = FilesystemModel()
        self.identity = IdentityModel()
        self.keyboard = KeyboardModel(self.root)
        self.locale = LocaleModel()
        self.mirror = MirrorModel()
        self.network = NetworkModel()
        self.packages = []
        self.proxy = ProxyModel()
        self.snaplist = SnapListModel()
        self.ssh = SSHModel()
        self.userdata = {}

        self._events = {
            name: asyncio.Event() for name in ALL_MODEL_NAMES
            }
        self.install_events = {
            self._events[name] for name in INSTALL_MODEL_NAMES
            }
        self.postinstall_events = {
            self._events[name] for name in POSTINSTALL_MODEL_NAMES
            }

    def configured(self, model_name):
        log.debug("model %s is configured", model_name)
        self._events[model_name].set()

    def get_target_groups(self):
        command = ['chroot', self.target, 'getent', 'group']
        if self.root != '/':
            del command[:2]
        cp = run_command(command, check=True)
        groups = set()
        for line in cp.stdout.splitlines():
            groups.add(line.split(':')[0])
        return groups

    def _cloud_init_config(self):
        config = {
            'growpart': {
                'mode': 'off',
                },
            'locale': self.locale.selected_language + '.UTF-8',
            'resize_rootfs': False,
        }
        if self.identity.hostname is not None:
            config['preserve_hostname'] = True
        user = self.identity.user
        if user:
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
                'lock_passwd': False,
                }
            if self.ssh.authorized_keys:
                user_info['ssh_authorized_keys'] = self.ssh.authorized_keys
            config['users'] = [user_info]
        else:
            if self.ssh.authorized_keys:
                config['ssh_authorized_keys'] = self.ssh.authorized_keys
        if self.ssh.install_server:
            config['ssh_pwauth'] = self.ssh.pwauth
        if self.snaplist.selections:
            cmds = []
            for selection in self.snaplist.selections:
                cmd = ['snap', 'install', '--channel=' + selection.channel]
                if selection.is_classic:
                    cmd.append('--classic')
                cmd.append(selection.name)
                cmds.append(' '.join(cmd))
            config['snap'] = {
                'commands': cmds,
                }
        userdata = copy.deepcopy(self.userdata)
        merge_config(userdata, config)
        return userdata

    def _cloud_init_files(self):
        # TODO, this should be moved to the in-target cloud-config seed so on
        # first boot of the target, it reconfigures datasource_list to none
        # for subsequent boots.
        # (mwhudson does not entirely know what the above means!)
        userdata = '#cloud-config\n' + yaml.dump(self._cloud_init_config())
        metadata = {'instance-id': str(uuid.uuid4())}
        config = yaml.dump({
            'datasource_list': ["None"],
            'datasource': {
                "None": {
                    'userdata_raw': userdata,
                    'metadata': metadata,
                    },
                },
            })
        files = [
            ('etc/cloud/cloud.cfg.d/99-installer.cfg', config, 0o600),
            ('etc/cloud/ds-identify.cfg', 'policy: enabled\n', 0o644),
            ]
        if self.identity.hostname is not None:
            hostname = self.identity.hostname.strip()
            files.extend([
                ('etc/hostname', hostname + "\n", 0o644),
                ('etc/hosts', HOSTS_CONTENT.format(hostname=hostname), 0o644),
                ])
        return files

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

    def _machine_id(self):
        with open('/etc/machine-id') as fp:
            return fp.read()

    def render(self, syslog_identifier):
        # Until https://bugs.launchpad.net/curtin/+bug/1876984 gets
        # fixed, the only way to get curtin to leave the network
        # config entirely alone is to omit the 'network' stage.
        stages = [
            stage for stage in CONFIG_BUILTIN['stages'] if stage != 'network'
            ]
        config = {
            'stages': stages,

            'sources': {
                'ubuntu00': 'cp:///media/filesystem'
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
            'grub': {
                'terminal': 'unmodified',
                'probe_additional_os': True
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
                    'content': self._machine_id(),
                    'permissions': 0o444,
                    },
                'media_info': {
                    'path': 'var/log/installer/media-info',
                    'content': self._media_info(),
                    'permissions': 0o644,
                    },
                },
            }

        if os.path.exists('/run/casper-md5check.json'):
            with open('/run/casper-md5check.json') as fp:
                config['write_files']['md5check'] = {
                    'path': 'var/log/installer/casper-md5check.json',
                    'content': fp.read(),
                    'permissions': 0o644,
                    }

        for model_name in INSTALL_MODEL_NAMES:
            model = getattr(self, model_name)
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
