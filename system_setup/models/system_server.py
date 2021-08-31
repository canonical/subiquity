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

from subiquity.models.subiquity import ModelNames, SubiquityModel

from subiquitycore.utils import is_wsl


from subiquity.models.locale import LocaleModel
from subiquity.models.identity import IdentityModel
from .wslconfbase import WSLConfigurationBaseModel
from .wslconfadvanced import WSLConfigurationAdvancedModel


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
        "wslconfbase",
    })

    def __init__(self, root, reconfigure=False):
        # TODO WSL: add base model here to prevent overlap
        if reconfigure:
            self.INSTALL_MODEL_NAMES = ModelNames({
                "locale",
                "wslconfadvanced",
            })
        # Parent class init is not called to not load models we don't need.
        self.root = root
        self.is_wsl = is_wsl()

        self.packages = []
        self.userdata = {}
        self.locale = LocaleModel()
        self.identity = IdentityModel()
        self.wslconfbase = WSLConfigurationBaseModel()
        self.wslconfadvanced = WSLConfigurationAdvancedModel()

        self._confirmation = asyncio.Event()
        self._confirmation_task = None

        self._configured_names = set()
        self._install_model_names = self.INSTALL_MODEL_NAMES
        self._postinstall_model_names = None
        self._cur_install_model_names = self.INSTALL_MODEL_NAMES.default_names
        self._cur_postinstall_model_names = None
        self._install_event = asyncio.Event()
        self._postinstall_event = asyncio.Event()

    def set_source_variant(self, variant):
        self._cur_install_model_names = \
            self._install_model_names.for_variant(variant)
        if self._cur_postinstall_model_names is not None:
            self._cur_postinstall_model_names = \
                self._postinstall_model_names.for_variant(variant)
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
