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
""" This model mainly manages the mirror selection but also covers all the
settings that can be found under the 'apt' autoinstall section.
Some settings are handled by Subiquity but others are directly forwarded to
curtin.

There are a few notions worth explaining related to mirror selection:

primary
-------
 * a "primary mirror" (or a "primary archive") is what curtin historically
 considers as the main repository where it can download Debian packages.
 Surprisingly, there is no notion of "secondary mirror". Instead there is the
 "security archive" where we download the packages from the -security pocket.

candidates
----------
 * a given install can have multiple primary candidate mirrors organized in a
 list. Providing multiple candidates increases the likelihood of having one
 tested successfully.
 When the process of mirror selection is run automatically, the candidates will
 be tested one after another until one passes the test. The one passing is then
 marked "elected".

staged
------
 * a primary mirror candidate can be "staged" or "staged for testing". The
 staged mirror is the one that will be used if subiquity decides to trigger a
 test of the apt configuration (a.k.a., mirror testing).

elected
-------
 * if a primary mirror candidate is marked "elected", then it is used when
 subiquity requests the final apt configuration. This means it will be used
 as the primary mirror during the install (only if we are online), and will
 end up in etc/apt/sources.list in the target system.

primary section
---------------
 * the "primary section" contains the different candidates for mirror
 selection. Today we support two different formats for this section, and the
 position of the primary section is what determines which format is used.
   * the legacy format, inherited from curtin, where the primary section is a
   direct child of the 'apt' section. In this format, the whole section denotes
   a single primary candidate so it cannot be used to specify multiple
   candidates.
   * the more modern format where the primary section is a child of the
   'mirror-selection' key (which itself is a child of 'apt'). In this format,
   the section is split into multiple "entries", each denoting a primary
   candidate.

primary entry
-------------
 * represents a fragment of the 'primary' autoinstall section. Each entry
 can be used as a primary candidate.
 * in the legacy format, the primary entry corresponds to the whole primary
 section.
 * in the new format, multiple primary entries make the primary section.
"""

import abc
import contextlib
import copy
import logging
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Set, Union
from urllib import parse

import attr
from curtin.commands.apt_config import (
    PORTS_ARCHES,
    PRIMARY_ARCHES,
    get_arch_mirrorconfig,
    get_mirror,
)
from curtin.config import merge_config

from subiquity.common.types import MirrorSelectionFallback

try:
    from curtin.distro import get_architecture
except ImportError:
    from curtin.util import get_architecture

log = logging.getLogger("subiquity.models.mirror")

DEFAULT_SUPPORTED_ARCHES_URI = "http://archive.ubuntu.com/ubuntu"
DEFAULT_PORTS_ARCHES_URI = "http://ports.ubuntu.com/ubuntu-ports"

LEGACY_DEFAULT_PRIMARY_SECTION = [
    {
        "arches": PRIMARY_ARCHES,
        "uri": DEFAULT_SUPPORTED_ARCHES_URI,
    },
    {
        "arches": ["default"],
        "uri": DEFAULT_PORTS_ARCHES_URI,
    },
]

DEFAULT = {
    "preserve_sources_list": False,
}


@attr.s(auto_attribs=True)
class BasePrimaryEntry(abc.ABC):
    """Base class to represent an entry from the 'primary' autoinstall
    section. A BasePrimaryEntry is expected to have a URI and therefore can be
    used as a primary candidate."""

    parent: "MirrorModel" = attr.ib(kw_only=True)

    def stage(self) -> None:
        self.parent.primary_staged = self

    def elect(self) -> None:
        self.parent.primary_elected = self

    @abc.abstractmethod
    def serialize_for_ai(self) -> Any:
        """Serialize the entry for autoinstall."""

    @abc.abstractmethod
    def supports_arch(self, arch: str) -> bool:
        """Tells whether the mirror claims to support the architecture
        specified."""


@attr.s(auto_attribs=True)
class PrimaryEntry(BasePrimaryEntry):
    """Represents a single primary mirror candidate; which can be converted
    to/from an entry of the 'apt->mirror-selection->primary' autoinstall
    section."""

    # Having uri set to None is only valid for a country mirror.
    uri: Optional[str] = None
    # When arches is None, it is assumed that the mirror is compatible with the
    # current CPU architecture.
    arches: Optional[List[str]] = None
    country_mirror: bool = attr.ib(kw_only=True, default=False)

    @classmethod
    def from_config(cls, config: Any, parent: "MirrorModel") -> "PrimaryEntry":
        if config == "country-mirror":
            return cls(parent=parent, country_mirror=True)
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
        if self.arches is None:
            return True
        return arch in self.arches

    def serialize_for_ai(self) -> Union[str, Dict[str, Any]]:
        if self.country_mirror:
            return "country-mirror"
        ret: Dict[str, Any] = {"uri": self.uri}
        if self.arches is not None:
            ret["arches"] = self.arches
        return ret


class LegacyPrimaryEntry(BasePrimaryEntry):
    """Represents a single primary mirror candidate; which can be converted
    to/from the whole 'apt->primary' autoinstall section (legacy format).
    The format is defined by curtin, so we make use of curtin to access
    the elements."""

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
            {"primary": self.config}, "primary", self.parent.architecture
        )
        config["uri"] = uri

    def mirror_is_default(self) -> bool:
        return self.uri == self.parent.default_mirror

    @classmethod
    def new_from_default(cls, parent: "MirrorModel") -> "LegacyPrimaryEntry":
        return cls(copy.deepcopy(LEGACY_DEFAULT_PRIMARY_SECTION), parent=parent)

    def serialize_for_ai(self) -> List[Any]:
        return self.config

    def supports_arch(self, arch: str) -> bool:
        # Curtin will always find a mirror ; albeit with the ["default"]
        # architectures.
        return True


def countrify_uri(uri: str, cc: str) -> str:
    """Return a URL where the host is prefixed with a country code."""
    parsed = parse.urlparse(uri)
    new = parsed._replace(netloc=cc + "." + parsed.netloc)
    return parse.urlunparse(new)


CandidateFilter = Callable[[BasePrimaryEntry], bool]


def filter_candidates(
    candidates: List[BasePrimaryEntry], *, filters: Sequence[CandidateFilter]
) -> Iterator[BasePrimaryEntry]:
    candidates_iter = iter(candidates)
    for filt in filters:
        candidates_iter = filter(filt, candidates_iter)
    return candidates_iter


class MirrorModel(object):
    def __init__(self):
        self.config = copy.deepcopy(DEFAULT)
        self.legacy_primary = False
        self.disabled_components: Set[str] = set()
        self.primary_elected: Optional[BasePrimaryEntry] = None
        self.primary_candidates: List[
            BasePrimaryEntry
        ] = self._default_primary_entries()

        self.primary_staged: Optional[BasePrimaryEntry] = None

        self.architecture = get_architecture()
        # Only useful for legacy primary sections
        self.default_mirror = LegacyPrimaryEntry.new_from_default(parent=self).uri

        # What to do if automatic mirror-selection fails.
        self.fallback = MirrorSelectionFallback.ABORT

    def _default_primary_entries(self) -> List[PrimaryEntry]:
        return [
            PrimaryEntry(parent=self, country_mirror=True),
            PrimaryEntry(
                uri=DEFAULT_SUPPORTED_ARCHES_URI, arches=PRIMARY_ARCHES, parent=self
            ),
            PrimaryEntry(
                uri=DEFAULT_PORTS_ARCHES_URI, arches=PORTS_ARCHES, parent=self
            ),
        ]

    def get_default_primary_candidates(
        self, legacy: Optional[bool] = None
    ) -> Sequence[BasePrimaryEntry]:
        want_legacy = legacy if legacy is not None else self.legacy_primary
        if want_legacy:
            return [LegacyPrimaryEntry.new_from_default(parent=self)]
        else:
            return self._default_primary_entries()

    def load_autoinstall_data(self, data):
        if "disable_components" in data:
            self.disabled_components = set(data.pop("disable_components"))

        if "primary" in data and "mirror-selection" in data:
            raise ValueError(
                "apt->primary and apt->mirror-selection are mutually exclusive."
            )
        self.legacy_primary = "primary" in data

        primary_candidates = self.get_default_primary_candidates()
        if "primary" in data:
            # Legacy sections only support a single candidate
            primary_candidates = [LegacyPrimaryEntry(data.pop("primary"), parent=self)]
        if "mirror-selection" in data:
            mirror_selection = data.pop("mirror-selection")
            if "primary" in mirror_selection:
                primary_candidates = []
                for section in mirror_selection["primary"]:
                    entry = PrimaryEntry.from_config(section, parent=self)
                    primary_candidates.append(entry)
        self.primary_candidates = primary_candidates
        if "fallback" in data:
            self.fallback = MirrorSelectionFallback(data.pop("fallback"))

        merge_config(self.config, data)

    def _get_apt_config_common(self) -> Dict[str, Any]:
        assert "disable_components" not in self.config
        assert "primary" not in self.config
        assert "fallback" not in self.config

        config = copy.deepcopy(self.config)
        config["disable_components"] = sorted(self.disabled_components)
        return config

    def _get_apt_config_using_candidate(
        self, candidate: BasePrimaryEntry
    ) -> Dict[str, Any]:
        config = self._get_apt_config_common()
        config["primary"] = candidate.config
        return config

    def get_apt_config_staged(self) -> Dict[str, Any]:
        assert self.primary_staged is not None
        return self._get_apt_config_using_candidate(self.primary_staged)

    def get_apt_config_elected(self) -> Dict[str, Any]:
        assert self.primary_elected is not None
        return self._get_apt_config_using_candidate(self.primary_elected)

    def get_apt_config(self, final: bool, has_network: bool) -> Dict[str, Any]:
        if not final:
            return self.get_apt_config_staged()
        if has_network:
            return self.get_apt_config_elected()
        # We want the final configuration but have no network. In this scenario
        # it is possible that we do not have an elected primary mirror.
        if self.primary_elected is not None:
            return self.get_apt_config_elected()
        # Look for the first compatible candidate with a URI.
        # There is no guarantee that it will be a working mirror since we have
        # not tested it. But it is fine because it will not be used during the
        # install. It will be placed in etc/apt/sources.list of the target
        # system.
        with contextlib.suppress(StopIteration):
            filters = [
                lambda c: c.uri is not None,
                lambda c: c.supports_arch(self.architecture),
            ]
            candidate = next(
                filter_candidates(self.primary_candidates, filters=filters)
            )
            return self._get_apt_config_using_candidate(candidate)
        # Our last resort is to include no primary section. Curtin will use
        # its own internal values.
        return self._get_apt_config_common()

    def set_country(self, cc):
        """Set the URI of country-mirror candidates."""
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
        """Add (or remove) a component (e.g., multiverse) from the list of
        disabled components."""
        comps = set(comps)
        if add:
            self.disabled_components |= comps
        else:
            self.disabled_components -= comps

    def create_primary_candidate(
        self, uri: Optional[str], country_mirror: bool = False
    ) -> BasePrimaryEntry:
        if self.legacy_primary:
            entry = LegacyPrimaryEntry.new_from_default(parent=self)
            entry.uri = uri
            return entry

        return PrimaryEntry(uri=uri, country_mirror=country_mirror, parent=self)

    def wants_geoip(self) -> bool:
        """Tell whether geoip results would be useful."""
        return next(self.country_mirror_candidates(), None) is not None

    def country_mirror_candidates(self) -> Iterator[BasePrimaryEntry]:
        def filt(candidate):
            if self.legacy_primary and candidate.mirror_is_default():
                return True
            elif not self.legacy_primary and candidate.country_mirror:
                return True
            return False

        return filter_candidates(self.primary_candidates, filters=[filt])

    def compatible_primary_candidates(self) -> Iterator[BasePrimaryEntry]:
        def filt(candidate):
            return candidate.supports_arch(self.architecture)

        return filter_candidates(self.primary_candidates, filters=[filt])

    def render(self):
        return {}

    def make_autoinstall(self):
        config = self._get_apt_config_common()
        if self.legacy_primary:
            # Only one candidate is supported
            if self.primary_elected is not None:
                to_serialize = self.primary_elected
            else:
                # In an offline autoinstall, there is no elected mirror.
                to_serialize = self.primary_candidates[0]
            config["primary"] = to_serialize.serialize_for_ai()
        else:
            primary = [c.serialize_for_ai() for c in self.primary_candidates]
            config["mirror-selection"] = {"primary": primary}
        config["fallback"] = self.fallback.value

        return config
