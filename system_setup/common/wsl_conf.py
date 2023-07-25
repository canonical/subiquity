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
import logging
import os
from configparser import ConfigParser

log = logging.getLogger("system_setup.common.wsl_conf")

WSL_SYSTEMD_BOOT_COMMAND = "/usr/libexec/wsl-systemd"

config_base_default = {
    "wsl": {
        "automount": {"root": "/mnt/", "options": ""},
        "network": {"generatehosts": "true", "generateresolvconf": "true"},
    }
}

config_adv_default = {
    "wsl": {
        "automount": {"enabled": "true", "mountfstab": "true"},
        "interop": {"enabled": "true", "appendwindowspath": "true"},
        "boot": {"command": ""},
    }
}

conf_type_to_file = {
    "wsl": "etc/wsl.conf",
}


def wsl_config_loader(pathname, config_ref, id):
    """
    Loads the configuration from the given file type,
    section and reference config.

    :param config_ref: dict, default entries
    :param id: string, the name of the section to load
    return the data loaded
    """
    data = {}
    config = ConfigParser()
    config.read(pathname)
    for conf_sec in config:
        if conf_sec in config_ref[id]:
            conf_sec_list = config[conf_sec]
            for conf_item in conf_sec_list:
                if conf_item in config_ref[id][conf_sec]:
                    # Handle systemd experimental feature (string -> bool)
                    if conf_sec.lower() == "boot" and conf_item.lower() == "command":
                        v = conf_sec_list[conf_item]
                        data["systemd_enabled"] = "false"
                        if v == WSL_SYSTEMD_BOOT_COMMAND:
                            data["systemd_enabled"] = "true"
                        continue
                    data[conf_sec.lower() + "_" + conf_item.lower()] = conf_sec_list[
                        conf_item
                    ]
    # This is the systemd value we converted
    data.pop("boot_command", None)
    return data


def default_loader(root_dir, is_advanced=False):
    """
    This will load the default WSL config for the given type.

    :param is_advanced: boolean, True if it is WSLConfigurationAdvanced,
                        else is WSLConfigurationBase
    """
    id = "wsl"
    pathname = os.path.join(root_dir, conf_type_to_file[id])
    if not os.path.exists(pathname):
        return {}
    conf_ref = config_adv_default if is_advanced else config_base_default
    data = wsl_config_loader(pathname, conf_ref, id)
    return data


def wsl_config_update(config_class, root_dir):
    """
    This update the configuration file for the given class.

    :param config_class: WSLConfigurationBase or WSLConfigurationAdvanced
    :param root_dir: string, the root directory of the WSL
    :param create_user: string, the user to create
    """
    temp_conf_default = {}
    temp_confname = config_class.__str__()
    if temp_confname.startswith("None"):
        return
    elif temp_confname.startswith("WSLConfigurationBase"):
        temp_conf_default = config_base_default
    elif temp_confname.startswith("WSLConfigurationAdvanced"):
        temp_conf_default = config_adv_default
    else:
        raise TypeError("Invalid type: {}".format(config_class))

    # update the config file
    for config_type in temp_conf_default:
        config_sections = temp_conf_default[config_type]

        config = ConfigParser()
        config.BasicInterpolation = None

        os.makedirs(os.path.join(root_dir, "etc"), exist_ok=True)
        conf_file = os.path.join(root_dir, conf_type_to_file[config_type])

        config.read(conf_file)

        for config_section in config_sections:
            config_settings = config_sections[config_section]
            for config_setting in config_settings:
                config_default_value = config_settings[config_setting]
                config_api_name = config_section.lower() + "_" + config_setting.lower()

                # on systemd, select correct API endpoint
                systemd_experimental_section = False
                if (
                    config_section.lower() == "boot"
                    and config_setting.lower() == "command"
                ):
                    systemd_experimental_section = True
                    config_api_name = "systemd_enabled"

                config_value = config_class.__dict__[config_api_name]
                if isinstance(config_value, bool):
                    config_value = str(config_value).lower()

                # map systemd bool -> boot command string and keep old value
                # if it was not set to wsl-systemd (user customized)
                if systemd_experimental_section:
                    v = ""
                    # Keep previous value set by user if the option is kept
                    # disabled and they set their own boot command.
                    if (
                        config.has_option("boot", "command")
                        and config["boot"]["command"] != WSL_SYSTEMD_BOOT_COMMAND
                    ):
                        v = config["boot"]["command"]
                    if config_value == "true":
                        v = WSL_SYSTEMD_BOOT_COMMAND
                    config_value = v

                # if the value for the setting is default value, drop it
                if config_default_value == config_value:
                    if config_section in config:
                        if config_setting in config[config_section]:
                            config.remove_option(config_section, config_setting)
                        # drop the section if it become empty
                        if config[config_section] == {}:
                            config.remove_section(config_section)
                else:
                    if config_section not in config:
                        config.add_section(config_section)
                    config[config_section][config_setting] = config_value

        # sort config in ascii order
        for section in config._sections:
            config._sections[section] = collections.OrderedDict(
                sorted(config._sections[section].items(), key=lambda t: t[0])
            )
        config._sections = collections.OrderedDict(
            sorted(config._sections.items(), key=lambda t: t[0])
        )

        with open(conf_file + ".new", "w+") as configfile:
            config.write(configfile)

        os.rename(conf_file + ".new", conf_file)
