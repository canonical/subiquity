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

import contextlib
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
    # Defaults to true for backward compatibility with existing autoinstall
    # configurations. Back then, then users were able to install third-party
    # drivers without this field.
    autoinstall_default = {"search_drivers": True}

    def __init__(self, app):
        super().__init__(app)
        self._handler = None
        self.source_path: Optional[str] = None
        self.ai_source_id: Optional[str] = None

    def make_autoinstall(self):
        return {
            "search_drivers": self.model.search_drivers,
            "id": self.model.current.id,
        }

    def load_autoinstall_data(self, data: Any) -> None:
        if data is None:
            # NOTE: The JSON schema does not allow data to be null in this
            # context. However, Subiquity bypasses the schema validation when
            # a section is set to null. So in practice, we can have data = None
            # here.
            data = {**self.autoinstall_default, "id": None}

        self.model.search_drivers = data.get("search_drivers", True)

        # At this point, the model has not yet loaded the sources from the
        # catalog. So we store the ID and lean on self.start to select the
        # current source accordingly.
        self.ai_source_id = data.get("id")

    def start(self):
        path = "/cdrom/casper/install-sources.yaml"
        if self.app.opts.source_catalog is not None:
            path = self.app.opts.source_catalog
        if not os.path.exists(path):
            return
        with open(path) as fp:
            self.model.load_from_file(fp)
        # Assign the current source if hinted by autoinstall.
        if self.ai_source_id is not None:
            self.model.current = self.model.get_matching_source(self.ai_source_id)
        self.app.hub.subscribe(
            (InstallerChannels.CONFIGURED, "locale"), self._set_locale
        )

    def _set_locale(self):
        current = self.app.base_model.locale.selected_language
        self.model.lang = current.split("_")[0]

    async def GET(self) -> SourceSelectionAndSetting:
        cur_lang = self.app.base_model.locale.selected_language
        cur_lang = cur_lang.rsplit(".", 1)[0]

        return SourceSelectionAndSetting(
            [convert_source(source, cur_lang) for source in self.model.sources],
            self.model.current.id,
            search_drivers=self.model.search_drivers,
        )

    def get_handler(
        self, variation_name: Optional[str] = None
    ) -> AbstractSourceHandler:
        handler = get_handler_for_source(
            sanitize_source(self.model.get_source(variation_name))
        )
        if self.app.opts.dry_run:
            handler = TrivialSourceHandler("/")
        return handler

    async def configured(self):
        await super().configured()
        self.app.base_model.set_source_variant(self.model.current.variant)

    async def POST(self, source_id: str, search_drivers: bool = False) -> None:
        self.model.search_drivers = search_drivers
        with contextlib.suppress(KeyError):
            self.model.current = self.model.get_matching_source(source_id)
        await self.configured()
