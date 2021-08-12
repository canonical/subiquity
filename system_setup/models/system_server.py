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

from subiquity.models.subiquity import SubiquityModel

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
    ALL_MODEL_NAMES = [
        "identity",
        "locale",
        "wslconf1",
    ]

    def __init__(self, root, reconfigure=False):
        if reconfigure:
            self.ALL_MODEL_NAMES = [
                "locale",
                "wslconf2",
            ]
        # Parent class init is not called to not load models we don't need.
        self.root = root
        self.is_wsl = is_wsl()

        self.debconf_selections = None
        self.filesystem = None
        self.kernel = None
        self.keyboard = None
        self.mirror = None
        self.network = None
        self.proxy = None
        self.snaplist = None
        self.ssh = None
        self.updates = None

        self.packages = []
        self.userdata = {}
        self.locale = LocaleModel()
        self.identity = IdentityModel()
        self.wslconf1 = WSLConfiguration1Model()
        self.wslconf2 = WSLConfiguration2Model()

        self.confirmation = asyncio.Event()

        self._events = {
            name: asyncio.Event() for name in self.ALL_MODEL_NAMES
        }
        self.postinstall_events = {
            self._events[name] for name in self.ALL_MODEL_NAMES
        }

    def configured(self, model_name):
        # We need to override the parent class as
        # *_MODEL_NAMES are global variables in server.py
        if model_name not in self.ALL_MODEL_NAMES:
            return
        self._events[model_name].set()
        stage = 'install'
        unconfigured = {
            mn for mn in self.ALL_MODEL_NAMES
            if not self._events[mn].is_set()
        }
        log.debug(
            "model %s for %s is configured, to go %s",
            model_name, stage, unconfigured)
