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
from typing import Any, Dict, List, Optional, Set
from urllib import parse

from curtin.commands.apt_config import (
    get_arch_mirrorconfig,
    get_mirror,
    PRIMARY_ARCHES,
    )
from curtin.config import merge_config

try:
    from curtin.distro import get_architecture
except ImportError:
    from curtin.util import get_architecture

log = logging.getLogger('subiquity.models.mirror')


DEFAULT_PRIMARY_SECTION = [
    {
        "arches": PRIMARY_ARCHES,
        "uri": "http://archive.ubuntu.com/ubuntu",
    }, {
        "arches": ["default"],
        "uri": "http://ports.ubuntu.com/ubuntu-ports",
    },
]


DEFAULT = {
    "preserve_sources_list": False,
}


class PrimarySection:
    """ Helper to manage a primary autoinstall section. """
    def __init__(self, config: List[Any], *, parent: "MirrorModel") -> None:
        self.parent = parent
        self.config = config

    def get_mirror(self) -> str:
        config = copy.deepcopy(self.parent.config)
        config["primary"] = self.config
        return get_mirror(config, "primary", self.parent.architecture)

    def set_mirror(self, uri: str) -> None:
        config = get_arch_mirrorconfig(
                {"primary": self.config},
                "primary", self.parent.architecture)
        config["uri"] = uri

    def mirror_is_default(self) -> bool:
        return self.get_mirror() == self.parent.default_mirror

    @classmethod
    def new_from_default(cls, parent: "MirrorModel") -> "PrimarySection":
        return cls(copy.deepcopy(DEFAULT_PRIMARY_SECTION), parent=parent)


def countrify_uri(uri: str, cc: str) -> str:
    """ Return a URL where the host is prefixed with a country code. """
    parsed = parse.urlparse(uri)
    new = parsed._replace(netloc=cc + '.' + parsed.netloc)
    return parse.urlunparse(new)


class MirrorModel(object):

    def __init__(self):
        self.config = copy.deepcopy(DEFAULT)
        self.disabled_components: Set[str] = set()
        self.primary_elected = PrimarySection.new_from_default(parent=self)
        self.primary_candidates: List[PrimarySection] = [
            self.primary_elected,
        ]

        self.primary_staged: Optional[PrimarySection] = None

        self.architecture = get_architecture()
        self.default_mirror = self.primary_candidates[0].get_mirror()

    def load_autoinstall_data(self, data):
        if "disable_components" in data:
            self.disabled_components = set(data.pop("disable_components"))
        if "primary" in data:
            # TODO support multiple candidates.
            self.primary_candidates = [
                    PrimarySection(data.pop("primary"), parent=self)
                    ]
            # TODO do not mark primary elected.
            self.primary_elected = self.primary_candidates[0]
        merge_config(self.config, data)

    def _get_apt_config_common(self) -> Dict[str, Any]:
        assert "disable_components" not in self.config
        assert "primary" not in self.config

        config = copy.deepcopy(self.config)
        config["disable_components"] = sorted(self.disabled_components)
        return config

    def get_apt_config_staged(self) -> Dict[str, Any]:
        assert self.primary_staged is not None

        config = self._get_apt_config_common()
        config["primary"] = self.primary_staged.config
        return config

    def get_apt_config_elected(self) -> Dict[str, Any]:
        config = self._get_apt_config_common()
        config["primary"] = self.primary_elected.config
        return config

    def set_country(self, cc):
        """ Set the URI of country-mirror candidates. """
        for candidate in self.primary_candidates:
            if candidate.mirror_is_default():
                uri = candidate.get_mirror()
                candidate.set_mirror(countrify_uri(uri, cc=cc))

    def disable_components(self, comps, add: bool) -> None:
        """ Add (or remove) a component (e.g., multiverse) from the list of
        disabled components. """
        comps = set(comps)
        if add:
            self.disabled_components |= comps
        else:
            self.disabled_components -= comps

    def replace_primary_candidates(self, uris: List[str]) -> None:
        self.primary_candidates.clear()
        for uri in uris:
            section = PrimarySection.new_from_default(parent=self)
            section.set_mirror(uri)
            self.primary_candidates.append(section)
        # NOTE: this is sometimes useful but it can be troublesome as well.
        self.primary_staged = None

    def assign_primary_elected(self, uri: str) -> None:
        self.primary_elected = PrimarySection.new_from_default(parent=self)
        self.primary_elected.set_mirror(uri)

    def wants_geoip(self) -> bool:
        """ Tell whether geoip results would be useful. """
        for candidate in self.primary_candidates:
            if candidate.is_default_mirror():
                return True
        return False

    def render(self):
        return {}

    def make_autoinstall(self):
        config = self._get_apt_config_common()
        config["primary"] = self.primary_elected.config
        return config
