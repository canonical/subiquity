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

import abc
import copy
import logging
from typing import Any, Dict, Iterator, List, Optional, Sequence, Set, Union
from urllib import parse

import attr

from curtin.commands.apt_config import (
    get_arch_mirrorconfig,
    get_mirror,
    PORTS_ARCHES,
    PRIMARY_ARCHES,
    )
from curtin.config import merge_config

try:
    from curtin.distro import get_architecture
except ImportError:
    from curtin.util import get_architecture

log = logging.getLogger('subiquity.models.mirror')

DEFAULT_SUPPORTED_ARCHES_URI = "http://archive.ubuntu.com/ubuntu"
DEFAULT_PORTS_ARCHES_URI = "http://ports.ubuntu.com/ubuntu-ports"

LEGACY_DEFAULT_PRIMARY_SECTION = [
    {
        "arches": PRIMARY_ARCHES,
        "uri": DEFAULT_SUPPORTED_ARCHES_URI,
    }, {
        "arches": ["default"],
        "uri": DEFAULT_PORTS_ARCHES_URI,
    },
]

DEFAULT = {
    "preserve_sources_list": False,
}


@attr.s(auto_attribs=True)
class PrimaryElement(abc.ABC):
    parent: "MirrorModel" = attr.ib(kw_only=True)

    def stage(self) -> None:
        self.parent.primary_staged = self

    def elect(self) -> None:
        self.parent.primary_elected = self

    @abc.abstractmethod
    def serialize_for_ai(self) -> Any:
        """ Serialize the element for autoinstall. """


@attr.s(auto_attribs=True)
class PrimaryEntry(PrimaryElement):
    # If the uri is None, it indicates a country-mirror that has not yet been
    # resolved.
    uri: Optional[str] = None
    # When arches is None, it is assumed that the mirror is compatible with the
    # current CPU architecture.
    arches: Optional[List[str]] = None

    @classmethod
    def from_config(cls, config: Any, parent: "MirrorModel") -> "PrimaryEntry":
        if config == "country-mirror":
            return cls(parent=parent)
        if config.get("uri", None) is None:
            raise ValueError("uri is mandatory")
        return cls(**config, parent=parent)

    @property
    def config(self) -> List[Dict[str, Any]]:
        assert self.uri is not None
        # Do not bother passing specific arches to curtin, we are passing a
        # single URI anyway.
        return [{"uri": self.uri, "arches": ["default"]}]

    def supports_arch(self, arch: str) -> bool:
        """ Tells whether the mirror claims to support the architecture
        specified. """
        if self.arches is None:
            return True
        return arch in self.arches

    def serialize_for_ai(self) -> Union[str, Dict[str, Any]]:
        # TODO also do it for already resolved ones
        if self.uri is None:
            return "country-mirror"
        ret: Dict[str, Any] = {"uri": self.uri}
        if self.arches is not None:
            ret["arches"] = self.arches
        return ret


class LegacyPrimarySection(PrimaryElement):
    """ Helper to manage a apt->primary autoinstall section.
    The format is the same as the format expected by curtin, no more, no less.
    """
    def __init__(self, config: List[Any], *, parent: "MirrorModel") -> None:
        self.config = config
        super().__init__(parent=parent)

    @property
    def uri(self) -> str:
        config = copy.deepcopy(self.parent.config)
        config["primary"] = self.config
        return get_mirror(config, "primary", self.parent.architecture)

    @uri.setter
    def uri(self, uri: str) -> None:
        config = get_arch_mirrorconfig(
                {"primary": self.config},
                "primary", self.parent.architecture)
        config["uri"] = uri

    def mirror_is_default(self) -> bool:
        return self.uri == self.parent.default_mirror

    @classmethod
    def new_from_default(cls, parent: "MirrorModel") -> "LegacyPrimarySection":
        return cls(copy.deepcopy(LEGACY_DEFAULT_PRIMARY_SECTION),
                   parent=parent)

    def serialize_for_ai(self) -> List[Any]:
        return self.config


def countrify_uri(uri: str, cc: str) -> str:
    """ Return a URL where the host is prefixed with a country code. """
    parsed = parse.urlparse(uri)
    new = parsed._replace(netloc=cc + '.' + parsed.netloc)
    return parse.urlunparse(new)


class MirrorModel(object):

    def __init__(self):
        self.config = copy.deepcopy(DEFAULT)
        self.legacy_primary = False
        self.disabled_components: Set[str] = set()
        self.primary_elected: Optional[PrimaryElement] = None
        self.primary_candidates: List[PrimaryElement] = \
            self._default_primary_entries()

        self.primary_staged: Optional[PrimaryElement] = None

        self.architecture = get_architecture()
        # Only useful for legacy primary sections
        self.default_mirror = \
            LegacyPrimarySection.new_from_default(parent=self).uri

    def _default_primary_entries(self) -> List[PrimaryEntry]:
        return [
            PrimaryEntry(parent=self),  # Country mirror
            PrimaryEntry(uri=DEFAULT_SUPPORTED_ARCHES_URI,
                         arches=PRIMARY_ARCHES, parent=self),
            PrimaryEntry(uri=DEFAULT_PORTS_ARCHES_URI,
                         arches=PORTS_ARCHES, parent=self),
        ]

    def get_default_primary_candidates(
            self, legacy: Optional[bool] = None) -> Sequence[PrimaryElement]:
        want_legacy = legacy if legacy is not None else self.legacy_primary
        if want_legacy:
            return [LegacyPrimarySection.new_from_default(parent=self)]
        else:
            return self._default_primary_entries()

    def load_autoinstall_data(self, data):
        self.legacy_primary = data.pop("version", 1) < 2
        if "disable_components" in data:
            self.disabled_components = set(data.pop("disable_components"))
        if "primary" in data:
            if self.legacy_primary:
                # Legacy sections only support a single candidate
                self.primary_candidates = \
                    [LegacyPrimarySection(data.pop("primary"), parent=self)]
            else:
                self.primary_candidates = []
                for section in data.pop("primary"):
                    entry = PrimaryEntry.from_config(section, parent=self)
                    self.primary_candidates.append(entry)
        else:
            self.primary_candidates = self.get_default_primary_candidates()

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
        assert self.primary_elected is not None

        config = self._get_apt_config_common()
        config["primary"] = self.primary_elected.config
        return config

    def set_country(self, cc):
        """ Set the URI of country-mirror candidates. """
        for candidate in self.country_mirror_candidates():
            if self.legacy_primary:
                candidate.uri = countrify_uri(candidate.uri, cc=cc)
            else:
                if self.architecture in PRIMARY_ARCHES:
                    uri = DEFAULT_SUPPORTED_ARCHES_URI
                else:
                    uri = DEFAULT_PORTS_ARCHES_URI
                candidate.uri = countrify_uri(uri, cc=cc)

    def disable_components(self, comps, add: bool) -> None:
        """ Add (or remove) a component (e.g., multiverse) from the list of
        disabled components. """
        comps = set(comps)
        if add:
            self.disabled_components |= comps
        else:
            self.disabled_components -= comps

    def create_primary_candidate(self, uri: Optional[str]) -> PrimaryElement:
        if self.legacy_primary:
            element = LegacyPrimarySection.new_from_default(parent=self)
            element.uri = uri
            return element

        return PrimaryEntry(uri=uri, parent=self)

    def wants_geoip(self) -> bool:
        """ Tell whether geoip results would be useful. """
        return next(self.country_mirror_candidates(), None) is not None

    def country_mirror_candidates(self) -> Iterator[PrimaryElement]:
        for candidate in self.primary_candidates:
            if self.legacy_primary and candidate.mirror_is_default():
                yield candidate
            elif not self.legacy_primary and candidate.uri is None:
                yield candidate

    def compatible_primary_candidates(self) -> Iterator[PrimaryElement]:
        for candidate in self.primary_candidates:
            if self.legacy_primary:
                yield candidate
            elif candidate.arches is None:
                yield candidate
            elif self.architecture in candidate.arches:
                yield candidate

    def render(self):
        return {}

    def make_autoinstall(self):
        config = self._get_apt_config_common()
        config["version"] = 1 if self.legacy_primary else 2
        if self.legacy_primary:
            # Only one candidate is supported
            if self.primary_elected is not None:
                to_serialize = self.primary_elected
            else:
                # In an offline autoinstall, there is no elected mirror.
                to_serialize = self.primary_candidates[0]
            config["primary"] = to_serialize.serialize_for_ai()
        else:
            config["primary"] = \
                [c.serialize_for_ai() for c in self.primary_candidates]

        return config
