# Copyright 2018 Canonical, Ltd.
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

import copy
import logging
from urllib import parse

from curtin.commands.apt_config import (
    get_arch_mirrorconfig,
    get_mirror,
    PRIMARY_ARCHES,
    )
from curtin.util import get_architecture

log = logging.getLogger('subiquitycore.models.mirror')


DEFAULT = {
    "preserve_sources_list": False,
    "primary": [
        {
            "arches": PRIMARY_ARCHES,
            "uri": "http://archive.ubuntu.com/ubuntu",
        },
        {
            "arches": ["default"],
            "uri": "http://ports.ubuntu.com/ubuntu-ports",
        },
        ],
}


def get_default_mirror():
    return get_mirror(DEFAULT, "primary", get_architecture())


class MirrorModel(object):

    def __init__(self):
        self.config = copy.deepcopy(DEFAULT)

    def set_country(self, cc):
        uri = self.get_mirror()
        if uri != get_default_mirror():
            return
        parsed = parse.urlparse(uri)
        new = parsed._replace(netloc=cc + '.' + parsed.netloc)
        self.set_mirror(parse.urlunparse(new))

    def get_mirror(self):
        return get_mirror(self.config, "primary", get_architecture())

    def set_mirror(self, mirror):
        config = get_arch_mirrorconfig(
            self.config, "primary", get_architecture())
        config["uri"] = mirror

    def render(self):
        return {
             'apt': self.config
            }
