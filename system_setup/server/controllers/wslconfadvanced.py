# Copyright 2021 Canonical, Ltd.
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

import attr
from os import path
import configparser
from subiquitycore.context import with_context

from subiquity.common.apidef import API
from subiquity.common.types import WSLConfigurationAdvanced
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.wsl_configuration_advanced')

# TODO WSL: remove all duplicates from WSL config base controller
class WSLConfigurationAdvancedController(SubiquityController):

    endpoint = API.wslconfadvanced

    autoinstall_key = model_name = "wslconfadvanced"
    autoinstall_schema = {
        'type': 'object',
        'properties': {
            'custom_path': {'type': 'string'},
            'custom_mount_opt': {'type': 'string'},
            'gen_host': {'type': 'boolean'},
            'gen_resolvconf': {'type': 'boolean'},
            'interop_enabled': {'type': 'boolean'},
            'interop_appendwindowspath': {'type': 'boolean'},
            'gui_theme': {'type': 'string'},
            'gui_followwintheme': {'type': 'boolean'},
            'legacy_gui': {'type': 'boolean'},
            'legacy_audio': {'type': 'boolean'},
            'adv_ip_detect': {'type': 'boolean'},
            'wsl_motd_news': {'type': 'boolean'},
            'automount': {'type': 'boolean'},
            'mountfstab': {'type': 'boolean'}
        },
        'required': [],
        'additionalProperties': False,
    }

    # this is a temporary simplified reference. The future complete reference
    # should use the default.json in `ubuntu-wsl-integration`.
    config_ref = {
        "wsl": {
            "automount": {
                "enabled": "automount",
                "mountfstab": "mountfstab",
                "root": "custom_path",
                "options": "custom_mount_opt",
            },
            "network": {
                "generatehosts": "gen_host",
                "generateresolvconf": "gen_resolvconf",
            },
            "interop": {
                "enabled": "interop_enabled",
                "appendwindowspath": "interop_appendwindowspath",
            }
        },
        "ubuntu": {
            "GUI": {
                "theme": "gui_theme",
                "followwintheme": "gui_followwintheme",
            },
            "Interop": {
                "guiintegration": "legacy_gui",
                "audiointegration": "legacy_audio",
                "advancedipdetection": "adv_ip_detect",
            },
            "Motd": {
                "wslnewsenabled": "wsl_motd_news",
            }
        }
    }

    def __init__(self, app):
        super().__init__(app)

        # load the config file
        data = {}
        if path.exists('/etc/wsl.conf'):
            wslconfig = configparser.ConfigParser()
            wslconfig.read('/etc/wsl.conf')
            for a in wslconfig:
                if a in self.config_ref['wsl']:
                    a_x = wslconfig[a]
                    for b in a_x:
                        if b in self.config_ref['wsl'][a]:
                            data[self.config_ref['wsl'][a][b]] = a_x[b]
        if path.exists('/etc/ubuntu-wsl.conf'):
            ubuntuconfig = configparser.ConfigParser()
            ubuntuconfig.read('/etc/ubuntu-wsl.conf')
            for a in ubuntuconfig:
                if a in self.config_ref['ubuntu']:
                    a_x = ubuntuconfig[a]
                    for b in a_x:
                        if b in self.config_ref['ubuntu'][a]:
                            data[self.config_ref['ubuntu'][a][b]] = a_x[b]
        if data:
            def bool_converter(x):
                return x == 'true'
            reconf_data = WSLConfigurationAdvanced(
                custom_path=data['custom_path'],
                custom_mount_opt=data['custom_mount_opt'],
                gen_host=bool_converter(data['gen_host']),
                gen_resolvconf=bool_converter(data['gen_resolvconf']),
                interop_enabled=bool_converter(data['interop_enabled']),
                interop_appendwindowspath=bool_converter(
                    data['interop_appendwindowspath']),
                gui_theme=data['gui_theme'],
                gui_followwintheme=bool_converter(data['gui_followwintheme']),
                legacy_gui=bool_converter(data['legacy_gui']),
                legacy_audio=bool_converter(data['legacy_audio']),
                adv_ip_detect=bool_converter(data['adv_ip_detect']),
                wsl_motd_news=bool_converter(data['wsl_motd_news']),
                automount=bool_converter(data['automount']),
                mountfstab=bool_converter(data['mountfstab']),
            )
            self.model.apply_settings(reconf_data, self.opts.dry_run)

    def load_autoinstall_data(self, data):
        if data is not None:
            reconf_data = WSLConfigurationAdvanced(
                custom_path=data['custom_path'],
                custom_mount_opt=data['custom_mount_opt'],
                gen_host=data['gen_host'],
                gen_resolvconf=data['gen_resolvconf'],
                interop_enabled=data['interop_enabled'],
                interop_appendwindowspath=data['interop_appendwindowspath'],
                gui_theme=data['gui_theme'],
                gui_followwintheme=data['gui_followwintheme'],
                legacy_gui=data['legacy_gui'],
                legacy_audio=data['legacy_audio'],
                adv_ip_detect=data['adv_ip_detect'],
                wsl_motd_news=data['wsl_motd_news'],
                automount=data['automount'],
                mountfstab=data['mountfstab']
            )
            self.model.apply_settings(reconf_data, self.opts.dry_run)

    @with_context()
    async def apply_autoinstall_config(self, context=None):
        pass

    def make_autoinstall(self):
        r = attr.asdict(self.model.wslconfadvanced)
        return r

    async def GET(self) -> WSLConfigurationAdvanced:
        data = WSLConfigurationAdvanced()
        if self.model.wslconfadvanced is not None:
            data.custom_path = self.model.wslconfadvanced.custom_path
            data.custom_mount_opt = self.model.wslconfadvanced.custom_mount_opt
            data.gen_host = self.model.wslconfadvanced.gen_host
            data.gen_resolvconf = self.model.wslconfadvanced.gen_resolvconf
            data.interop_enabled = self.model.wslconfadvanced.interop_enabled
            data.interop_appendwindowspath = \
                self.model.wslconfadvanced.interop_appendwindowspath
            data.gui_theme = self.model.wslconfadvanced.gui_theme
            data.gui_followwintheme = self.model.wslconfadvanced.gui_followwintheme
            data.legacy_gui = self.model.wslconfadvanced.legacy_gui
            data.legacy_audio = self.model.wslconfadvanced.legacy_audio
            data.adv_ip_detect = self.model.wslconfadvanced.adv_ip_detect
            data.wsl_motd_news = self.model.wslconfadvanced.wsl_motd_news
            data.automount = self.model.wslconfadvanced.automount
            data.mountfstab = self.model.wslconfadvanced.mountfstab
        return data

    async def POST(self, data: WSLConfigurationAdvanced):
        self.model.apply_settings(data, self.opts.dry_run)
        self.configured()
