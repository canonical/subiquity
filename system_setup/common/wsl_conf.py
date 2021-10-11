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

import collections
import os
import logging
from configparser import ConfigParser

log = logging.getLogger("system_setup.common.wsl_conf")

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

conf_type_to_file = {
    "wsl": "/etc/wsl.conf",
    "ubuntu": "/etc/ubuntu-wsl.conf"
}


def wsl_config_loader(data, config_ref, id):
    """
    Loads the configuration from the given file type,
    section and reference config.

    :param data: dict, the data to load into
    :param pathname: string, the path to the file to load
    :param id: string, the name of the section to load
    """
    pathname = conf_type_to_file[id]
    if not os.path.exists(pathname):
        return data
    config = ConfigParser()
    config.read(pathname)
    for conf_sec in config:
        if conf_sec in config_ref[id]:
            conf_sec_list = config[conf_sec]
            for conf_item in conf_sec_list:
                if conf_item in config_ref[id][conf_sec]:
                    data[conf_sec.lower()
                         + "_" + conf_item.lower()] = \
                             conf_sec_list[conf_item]
    return data


def default_loader(is_advanced=False):
    """
    This will load the default WSL config for the given type.

    :param is_advanced: boolean, True if it is WSLConfigurationAdvanced,
                        else is WSLConfigurationBase
    """
    data = {}
    conf_ref = config_adv_default if is_advanced else config_base_default
    data = wsl_config_loader(data, conf_ref, "wsl")
    if is_advanced:
        data = \
            wsl_config_loader(data, conf_ref, "ubuntu")
    return data


def wsl_config_update(config_class, root_dir, default_user=None):
    """
    This update the configuration file for the given class.

    :param config_class: WSLConfigurationBase or WSLConfigurationAdvanced
    :param root_dir: string, the root directory of the WSL
    :param create_user: string, the user to create
    """
    temp_conf_default = {}
    temp_confname = config_class.__str__()
    if temp_confname.startswith("WSLConfigurationBase"):
        temp_conf_default = config_base_default
    elif temp_confname.startswith("WSLConfigurationAdvanced"):
        temp_conf_default = config_adv_default
    else:
        raise TypeError("Invalid type name.")

    # update the config file
    for config_type in temp_conf_default:
        config_sections = temp_conf_default[config_type]

        config = ConfigParser()
        config.BasicInterpolcation = None

        os.makedirs(os.path.join(root_dir, "etc"), exist_ok=True)
        conf_file = os.path.join(root_dir, conf_type_to_file[config_type][1:])

        config.read(conf_file)

        for config_section in config_sections:
            config_settings = config_sections[config_section]
            for config_setting in config_settings:
                config_default_value = config_settings[config_setting]
                config_api_name = \
                    config_section.lower() + "_" + config_setting.lower()
                config_value = config_class.__dict__[config_api_name]
                if isinstance(config_value, bool):
                    config_value = str(config_value).lower()
                # if the value for the setting is default value, drop it
                if config_default_value == config_value:
                    if config_section in config:
                        if config_setting in config[config_section]:
                            config.remove_option(config_section,
                                                 config_setting)
                        # drop the section if it become empty
                        if config[config_section] == {}:
                            config.remove_section(config_section)
                else:
                    if config_section not in config:
                        config.add_section(config_section)
                    config[config_section][config_setting] = config_value

        if config_type == "wsl" and default_user is not None:
            if "user" not in config:
                config.add_section("user")
            config["user"]["default"] = default_user

        # sort config in ascii order
        for section in config._sections:
            config._sections[section] = \
                collections.OrderedDict(
                    sorted(config._sections[section].items(),
                           key=lambda t: t[0]))
        config._sections = \
            collections.OrderedDict(sorted(config._sections.items(),
                                           key=lambda t: t[0]))

        with open(conf_file + ".new", 'w+') as configfile:
            config.write(configfile)

        os.rename(conf_file + ".new", conf_file)
