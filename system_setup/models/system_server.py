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
import logging
import os
import sys
from subiquity.common.resources import resource_path

from curtin.commands.install import CONFIG_BUILTIN

from subiquity.models.subiquity import ModelNames, SubiquityModel

from subiquitycore.utils import is_wsl


from subiquity.models.locale import LocaleModel
from subiquity.models.identity import IdentityModel
from .wslconf1 import WSLConfiguration1Model
from .wslconf2 import WSLConfiguration2Model


log = logging.getLogger('system_setup.models.system_server')

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


class SystemSetupModel(SubiquityModel):
    """The overall model for subiquity."""

    target = '/'

    # Models that will be used in WSL system setup
    INSTALL_MODEL_NAMES = ModelNames({
        "locale",
        "identity",
        "wslconf1",
    })

    def __init__(self, root, reconfigure=False):
        if reconfigure:
            self.INSTALL_MODEL_NAMES = ModelNames({
                "locale",
                "wslconf2",
            })
        # Parent class init is not called to not load models we don't need.
        self.root = root
        self.is_wsl = is_wsl()

        self.packages = []
        self.userdata = {}
        self.locale = LocaleModel()
        self.identity = IdentityModel()
        self.wslconf1 = WSLConfiguration1Model()
        self.wslconf2 = WSLConfiguration2Model()

        self._confirmation = asyncio.Event()
        self._confirmation_task = None

        self._configured_names = set()
        self._install_model_names = self.INSTALL_MODEL_NAMES
        self._postinstall_model_names = None
        self._cur_install_model_names = self.INSTALL_MODEL_NAMES.default_names
        self._cur_postinstall_model_names = None
        self._install_event = asyncio.Event()
        self._postinstall_event = asyncio.Event()
        self._postinstall_event.set()  # no postinstall for WSL

    def set_source_variant(self, variant):
        self._cur_install_model_names = \
            self._install_model_names.for_variant(variant)
        unconfigured_install_model_names = \
            self._cur_install_model_names - self._configured_names
        if unconfigured_install_model_names:
            if self._install_event.is_set():
                self._install_event = asyncio.Event()
            if self._confirmation_task is not None:
                self._confirmation_task.cancel()
        else:
            self._install_event.set()

    def configured(self, model_name):
        self._configured_names.add(model_name)
        if model_name in self._cur_install_model_names:
            stage = 'install'
            names = self._cur_install_model_names
            event = self._install_event
        else:
            return
        unconfigured = names - self._configured_names
        log.debug(
            "model %s for %s stage is configured, to go %s",
            model_name, stage, unconfigured)
        if not unconfigured:
            event.set()

    def render(self, syslog_identifier):
        # Until https://bugs.launchpad.net/curtin/+bug/1876984 gets
        # fixed, the only way to get curtin to leave the network
        # config entirely alone is to omit the 'network' stage.
        stages = [
            stage for stage in CONFIG_BUILTIN['stages'] if stage != 'network'
            ]
        curhooks_commands_network = "false"
        if hasattr(self, 'network'):
            curhooks_commands_network = str(self.network.has_network).lower()
        config = {
            'stages': stages,

            'sources': {
                'ubuntu00': 'cp:///media/filesystem'
                },

            'curthooks_commands': {
                '001-configure-apt': [
                    resource_path('bin/subiquity-configure-apt'),
                    sys.executable, curhooks_commands_network,
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

        return config
