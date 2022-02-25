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
import functools
import logging

from subiquity.models.subiquity import SubiquityModel
from subiquity.models.locale import LocaleModel
from subiquity.models.identity import IdentityModel
from subiquity.server.types import InstallerChannels

from .wslconfbase import WSLConfigurationBaseModel
from .wslconfadvanced import WSLConfigurationAdvancedModel


log = logging.getLogger('system_setup.models.system_setup')

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

    def __init__(self, root, hub, install_model_names,
                 postinstall_model_names):
        # Parent class init is not called to not load models we don't need.
        self.root = root
        if root != '/':
            self.target = root
            self.chroot_prefix = []

        self.packages = []
        self.userdata = {}
        self.locale = LocaleModel(self.chroot_prefix)
        self.identity = IdentityModel()
        self.wslconfbase = WSLConfigurationBaseModel()
        self.wslconfadvanced = WSLConfigurationAdvancedModel()

        self._confirmation = asyncio.Event()
        self._confirmation_task = None

        self._configured_names = set()
        self._install_model_names = install_model_names
        self._postinstall_model_names = postinstall_model_names
        self._cur_install_model_names = install_model_names.default_names
        self._cur_postinstall_model_names = \
            postinstall_model_names.default_names
        self._install_event = asyncio.Event()
        self._postinstall_event = asyncio.Event()
        all_names = set()
        all_names.update(install_model_names.all())
        all_names.update(postinstall_model_names.all())
        for name in all_names:
            hub.subscribe(
                (InstallerChannels.CONFIGURED, name),
                functools.partial(self._configured, name))
