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

log = logging.getLogger("system_setup.common.conf")


class WSLConfig:
    def __init__(self, inst_type,  conf_file):
        self.inst_type = inst_type
        self.conf_file = conf_file

        self.config = ConfigParser()
        self.config.BasicInterpolcation = None
        self.config.read(conf_file)

    def update(self, config_section, config_setting, config_value):
        self.config[config_section][config_setting] = config_value
        with open(self.conf_file, 'w') as configfile:
            self.config.write(configfile)


class WSLConfigHandler:

    def __init__(self, is_dry_run):
        self.is_dry_run = is_dry_run
        self.ubuntu_conf = \
            WSLConfig("ubuntu", "/etc/ubuntu-wsl.conf")
        self.wsl_conf = WSLConfig("wsl", "/etc/wsl.conf")

    def _select_config(self, type_input):
        type_input = type_input.lower()
        if type_input == "ubuntu":
            return self.ubuntu_conf
        elif type_input == "wsl":
            return self.wsl_conf
        else:
            raise ValueError("Invalid config name. Please check again.")

    def _update(self, config_type, section, config, value):
        self._select_config(config_type).update(section, config, value)

    def update(self, config_name, value):
        if self.is_dry_run:
            log.debug("mimicking setting config %s with %s",
                      config_name, value)
            return
        config_name_set = config_name.split(".")
        # it should always be three level: type, section, and config.
        if len(config_name_set) == 3:
            self._update(config_name_set[0], config_name_set[1],
                         config_name_set[2], value)
        elif len(config_name_set) == 2:  # if type is missing, guess
            if not (config_name_set[0] in ("ubuntu", "wsl")
                    and config_name_set[1] == "*"):  # no top level wild card
                type_name = "ubuntu" if config_name_set[0] in (
                    "Motd", "Interop", "GUI") else "wsl"
                self._update(type_name, config_name_set[0],
                             config_name_set[1], value)
        else:  # invaild name
            raise ValueError("Invalid config name '{}'.".format(config_name))
