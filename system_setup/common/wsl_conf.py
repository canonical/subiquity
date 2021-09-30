#!/usr/bin/env python3
# Copyright 2015-2021 Canonical, Ltd.
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

#    original code from ubuntuwslctl.core.loader
#    Copyright (C) 2021 Canonical Ltd.

import logging
from configparser import ConfigParser
from os import path

log = logging.getLogger("system_setup.common.wsl_conf")

config_base_ref = {
    "wsl": {
        "automount": {
            "root": "custom_path",
            "options": "custom_mount_opt",
        },
        "network": {
            "generatehosts": "gen_host",
            "generateresolvconf": "gen_resolvconf",
        },
    }
}

config_base_default = {
    "wsl": {
        "automount": {
            "root": "/mnt/",
            "options": ""
        },
        "network": {
            "generatehosts": "true",
            "generateresolvconf": "true"
        }
    }
}

config_adv_ref = {
    "wsl": {
        "automount": {
            "enabled": "automount",
            "mountfstab": "mountfstab",
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

config_adv_default = {
    "wsl": {
        "automount": {
            "enabled": "true",
            "mountfstab": "true"
        },
        "interop": {
            "enabled": "true",
            "appendwindowspath": "true"
        }
    },
    "ubuntu": {
        "GUI": {
            "theme": "default",
            "followwintheme": "false"
        },
        "Interop": {
            "guiintegration": "false",
            "audiointegration": "false",
            "advancedipdetection": "false"
        },
        "Motd": {
            "wslnewsenabled": "true"
        }
    }
}


def wsl_config_loader(data, pathname, config_ref, id):
    if path.exists(pathname):
        config = ConfigParser()
        config.read(pathname)
        for conf_sec in config:
            if conf_sec in config_ref[id]:
                conf_sec_list = config[conf_sec]
                for conf_item in conf_sec_list:
                    if conf_item in config_ref[id][conf_sec]:
                        data[config_ref[id][conf_sec][conf_item]] = \
                                conf_sec_list[conf_item]
    return data


def default_loader(is_advanced):
    data = {}
    conf_ref = config_adv_ref if is_advanced else config_base_ref
    data = wsl_config_loader(data, "/etc/wsl.conf", conf_ref, "wsl")
    if is_advanced:
        data = \
            wsl_config_loader(data, "/etc/ubuntu-wsl.conf", conf_ref, "ubuntu")
    return data


class WSLConfig:
    def __init__(self, conf_file):
        self.conf_file = conf_file

        self.config = ConfigParser()
        self.config.BasicInterpolcation = None
        self.config.read(conf_file)

    def drop_if_exists(self, config_section, config_setting):
        if config_setting in self.config[config_section]:
            self.config.remove_option(config_section, config_setting)
            with open(self.conf_file, 'w') as configfile:
                self.config.write(configfile)

    def update(self, config_section, config_setting, config_value):
        self.config[config_section][config_setting] = config_value
        with open(self.conf_file, 'w') as configfile:
            self.config.write(configfile)


class WSLConfigHandler:

    def __init__(self, is_dry_run):
        self.is_dry_run = is_dry_run
        self.ubuntu_conf = \
            WSLConfig("/etc/ubuntu-wsl.conf")
        self.wsl_conf = WSLConfig("/etc/wsl.conf")

    def _select_config(self, type_input):
        type_input = type_input.lower()
        if type_input == "ubuntu":
            return self.ubuntu_conf
        elif type_input == "wsl":
            return self.wsl_conf
        else:
            raise ValueError("Invalid config type '{}'.".format(type_input))

    def update(self, config_class):
        if self.is_dry_run:
            log.debug("mimicking setting config %s",
                      config_class)
        temp_conf_ref = {}
        temp_conf_default = {}
        test_confname = config_class.__str__()
        if test_confname.startswith("WSLConfigurationBase"):
            temp_conf_ref = config_base_ref
            temp_conf_default = config_base_default
        elif test_confname.startswith("WSLConfigurationAdvanced"):
            temp_conf_ref = config_adv_ref
            temp_conf_default = config_adv_default
        else:
            raise TypeError("Invalid type name.")
        if self.is_dry_run:
            return
        for config_type in temp_conf_ref:
            config_sections = temp_conf_ref[config_type]
            for config_section in config_sections:
                config_settings = config_sections[config_section]
                for config_setting in config_settings:
                    config_realname = config_settings[config_setting]
                    config_value = config_class.__dict__[config_realname]
                    if temp_conf_default[config_type][config_section][
                            config_setting] == config_value:
                        self._select_config(config_type). \
                            drop_if_exists(config_section,
                                           config_setting)
                    else:
                        self._select_config(config_type). \
                            update(config_section,
                                   config_setting,
                                   config_value)
