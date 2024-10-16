# Copyright 2021 Canonical, Ltd.
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

import enum
import logging
import os
import typing

import attr
import yaml

from subiquity.common.serialize import Serializer

log = logging.getLogger("subiquity.models.source")


@attr.s(auto_attribs=True, kw_only=True)
class CatalogEntryVariation:
    path: str = ""
    size: int
    snapd_system_label: typing.Optional[str] = None


@attr.s(auto_attribs=True, kw_only=True)
class CatalogEntry:
    variant: str
    id: str
    name: typing.Dict[str, str]
    description: typing.Dict[str, str]
    path: str = ""
    size: int
    type: typing.Optional[str]
    default: bool = False
    locale_support: str = attr.ib(default="locale-only")
    preinstalled_langs: typing.List[str] = attr.Factory(list)
    snapd_system_label: typing.Optional[str] = None
    variations: typing.Dict[str, CatalogEntryVariation] = attr.Factory(dict)

    def __attrs_post_init__(self):
        if not self.variations:
            self.variations["default"] = CatalogEntryVariation(
                path=self.path,
                size=self.size,
                snapd_system_label=self.snapd_system_label,
            )


# It is possible that on release day the default (i.e. generic) kernel
# will not support ZFS or NVidia drivers. In this case, if the target
# system and the user's choices combine to want to use these features,
# we install a "bridge" kernel instead (when as the generic/default
# kernel does support these features, the bridge kernel metapackage
# will be switched to referencing the default kernel metapackage). All
# the details about this are stored in the source catalog on the ISO.


class BridgeKernelReason(enum.Enum):
    # When bridge_reasons contains "drivers", some driver packages are known to
    # be behind, so we should fall back to the bridge kernel.
    DRIVERS = "drivers"
    # When bridge_reasons contains "zfs", we should use the bridge kernel as
    # the default kernel is not yet known to the kernel team to be sufficiently
    # stable.
    ZFS = "zfs"


@attr.s(auto_attribs=True, kw_only=True)
class KernelInfo:
    default: str
    bridge: typing.Optional[str] = None
    bridge_reasons: typing.List[BridgeKernelReason] = attr.Factory(list)


@attr.s(auto_attribs=True, kw_only=True)
class SourceCatalog:
    version: int
    sources: typing.List[CatalogEntry]
    kernel: KernelInfo


legacy_server_entry = CatalogEntry(
    variant="server",
    id="synthesized",
    name={"en": "Ubuntu Server"},
    description={"en": "the default"},
    path="/media/filesystem",
    type="cp",
    default=True,
    size=2 << 30,
    locale_support="locale-only",
    variations={
        "default": CatalogEntryVariation(path="/media/filesystem", size=2 << 30),
    },
)

_serializer = Serializer(ignore_unknown_fields=True, serialize_enums_by="value")


class SourceModel:
    def __init__(self):
        self._dir = "/cdrom/casper"
        self.current = legacy_server_entry
        self.catalog = SourceCatalog(
            version=1,
            sources=[self.current],
            kernel=KernelInfo(default="linux-generic"),
        )
        self.lang = None
        self.search_drivers = False

    def load_from_file(self, fp):
        self._dir = os.path.dirname(fp.name)
        self.current = None
        content = yaml.safe_load(fp)
        if isinstance(content, list):
            self.catalog = SourceCatalog(
                version=1,
                sources=_serializer.deserialize(typing.List[CatalogEntry], content),
                kernel=KernelInfo(default="linux-generic"),
            )
        else:
            self.catalog = _serializer.deserialize(SourceCatalog, content)
        for entry in self.catalog.sources:
            if entry.default:
                self.current = entry
        log.debug("loaded %d sources from %r", len(self.catalog.sources), fp.name)
        if self.current is None:
            self.current = self.catalog.sources[0]

    def get_matching_source(self, id_: str) -> CatalogEntry:
        """Return a source object that has the ID requested."""
        for source in self.catalog.sources:
            if source.id == id_:
                return source
        raise KeyError

    def get_source(
        self, variation_name: typing.Optional[str] = None
    ) -> typing.Optional[str]:
        scheme = self.current.type
        if scheme is None:
            return None
        if variation_name is None:
            variation = next(iter(self.current.variations.values()))
        else:
            variation = self.current.variations[variation_name]
        path = os.path.join(self._dir, variation.path)
        if self.current.preinstalled_langs:
            base, ext = os.path.splitext(path)
            if self.lang in self.current.preinstalled_langs:
                suffix = self.lang
            else:
                suffix = "no-languages"
            path = base + "." + suffix + ext
        return f"{scheme}://{path}"

    def render(self):
        return {}
