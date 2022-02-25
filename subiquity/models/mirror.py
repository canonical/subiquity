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
try:
    from curtin.distro import get_architecture
except ImportError:
    from curtin.util import get_architecture

log = logging.getLogger('subiquity.models.mirror')


DEFAULT = {
    "disable_components": [],
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


class MirrorModel(object):

    def __init__(self):
        self.config = copy.deepcopy(DEFAULT)
        self.architecture = get_architecture()
        self.default_mirror = self.get_mirror()

    def get_apt_config(self):
        return copy.deepcopy(self.config)

    def mirror_is_default(self):
        return self.get_mirror() == self.default_mirror

    def set_country(self, cc):
        if not self.mirror_is_default():
            return
        uri = self.get_mirror()
        parsed = parse.urlparse(uri)
        new = parsed._replace(netloc=cc + '.' + parsed.netloc)
        self.set_mirror(parse.urlunparse(new))

    def get_mirror(self):
        return get_mirror(self.config, "primary", self.architecture)

    def set_mirror(self, mirror):
        config = get_arch_mirrorconfig(
            self.config, "primary", self.architecture)
        config["uri"] = mirror

    def disable_components(self, comps, add):
        dc = set(self.config.get('disable_components', []))
        comps = set(comps)
        if add:
            dc |= comps
        else:
            dc -= comps
        self.config['disable_components'] = list(dc)

    def render(self):
        return {}
