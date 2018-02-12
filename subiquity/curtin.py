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

from collections import OrderedDict
import logging
import os

import yaml


log = logging.getLogger("subiquity.curtin")

CURTIN_SEARCH_PATH = ['/usr/local/curtin/bin', '/usr/bin']
CURTIN_INSTALL_LOG = '/tmp/subiquity-curtin-install.log'
CURTIN_POSTINSTALL_LOG = '/tmp/subiquity-curtin-postinstall.log'


def setup_yaml():
    """ http://stackoverflow.com/a/8661021 """
    represent_dict_order = lambda self, data:  self.represent_mapping('tag:yaml.org,2002:map', data.items())
    yaml.add_representer(OrderedDict, represent_dict_order)

setup_yaml()


def curtin_find_curtin():
    for p in CURTIN_SEARCH_PATH:
        curtin = os.path.join(p, 'curtin')
        if os.path.exists(curtin):
            log.debug('curtin found at: {}'.format(curtin))
            return curtin
    # This ensures we fail when we attempt to run curtin
    # but it's not present
    return '/bin/false'


def curtin_install_cmd(config):
    return [curtin_find_curtin(), '-vvv', '--showtrace', '-c', config, 'install']
