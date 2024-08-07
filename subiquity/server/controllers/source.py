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

import logging
import os
from typing import Any, Optional

from curtin.commands.extract import (
    AbstractSourceHandler,
    TrivialSourceHandler,
    get_handler_for_source,
)
from curtin.util import sanitize_source

from subiquity.common.apidef import API
from subiquity.common.types import SourceSelection, SourceSelectionAndSetting
from subiquity.server.controller import SubiquityController
from subiquity.server.types import InstallerChannels

SOURCES_DEFAULT_PATH = "/cdrom/casper/install-sources.yaml"

log = logging.getLogger("subiquity.server.controllers.source")


def _translate(d, lang):
    if lang:
        for lang in lang, lang.split("_", 1)[0]:
            if lang in d:
                return d[lang]
    return _(d["en"])


def convert_source(source, lang):
    size = max([v.size for v in source.variations.values()])
    return SourceSelection(
        name=_translate(source.name, lang),
        description=_translate(source.description, lang),
        id=source.id,
        size=size,
        variant=source.variant,
        default=source.default,
    )


SEARCH_DRIVERS_AUTOINSTALL_DEFAULT = object()


class SourceController(SubiquityController):
    model_name = "source"

    endpoint = API.source

    autoinstall_key = "source"
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "search_drivers": {
                "type": "boolean",
            },
            "id": {
                "type": "string",
            },
        },
    }

    def __init__(self, app):
        super().__init__(app)
        self._handler = None
        self.source_path: Optional[str] = None
        self._configured: bool = False

        path = SOURCES_DEFAULT_PATH
        if self.app.opts.source_catalog is not None:
            path = self.app.opts.source_catalog
        if os.path.exists(path):
            with open(path) as fp:
                self.model.load_from_file(fp)

    def make_autoinstall(self):
        return {
            "search_drivers": self.model.search_drivers,
            "id": self.model.current.id,
        }

    def load_autoinstall_data(self, data: Optional[dict[str, Any]]) -> None:
        if data is None:
            data = {}

        # Defaults to almost-true for backward compatibility with existing autoinstall
        # configurations. Back then, then users were able to install third-party drivers
        # without this field. The "almost-true" part is that search_drivers defaults to
        # False for core boot classic installs.
        self.model.search_drivers = data.get(
            "search_drivers", SEARCH_DRIVERS_AUTOINSTALL_DEFAULT
        )

        # Assign the current source if hinted by autoinstall.
        if id := data.get("id"):
            self.model.current = self.model.get_matching_source(id)

    def start(self):
        self.app.hub.subscribe(
            (InstallerChannels.CONFIGURED, "locale"), self._set_locale
        )

    def _set_locale(self):
        current = self.app.base_model.locale.selected_language
        self.model.lang = current.split("_")[0]

    async def GET(self) -> SourceSelectionAndSetting:
        cur_lang = self.app.base_model.locale.selected_language
        cur_lang = cur_lang.rsplit(".", 1)[0]

        search_drivers = self.model.search_drivers
        if search_drivers is SEARCH_DRIVERS_AUTOINSTALL_DEFAULT:
            search_drivers = True

        return SourceSelectionAndSetting(
            [convert_source(source, cur_lang) for source in self.model.sources],
            self.model.current.id,
            search_drivers=search_drivers,
        )

    def get_handler(
        self, variation_name: Optional[str] = None
    ) -> AbstractSourceHandler:
        handler = get_handler_for_source(
            sanitize_source(self.model.get_source(variation_name))
        )
        if handler is not None and self.app.opts.dry_run:
            handler = TrivialSourceHandler("/")
        return handler

    async def configured(self):
        await super().configured()
        self._configured = True
        self.app.base_model.set_source_variant(self.model.current.variant)

    async def POST(self, source_id: str, search_drivers: bool = False) -> None:
        # Marking the source model configured has an effect on many of the
        # other controllers. Oftentimes, it would involve cancelling and
        # restarting various operations.
        # Let's try not to trigger the event again if we are not changing any
        # of the settings.
        changed = False
        if self.model.search_drivers != search_drivers:
            changed = True
            self.model.search_drivers = search_drivers

        try:
            new_source = self.model.get_matching_source(source_id)
        except KeyError:
            # TODO going forward, we should probably stop ignoring unmatched
            # sources.
            log.warning("unable to find '%s' in sources catalog", source_id)
            pass
        else:
            if self.model.current != new_source:
                changed = True
                self.model.current = new_source

        if changed or not self._configured:
            await self.configured()
