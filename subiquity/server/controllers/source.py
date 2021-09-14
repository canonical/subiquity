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

import os

from subiquity.common.apidef import API
from subiquity.common.types import (
    SourceSelection,
    SourceSelectionAndSetting,
    )
from subiquity.server.controller import SubiquityController


def _translate(d, lang):
    if lang:
        for lang in lang, lang.split('_', 1)[0]:
            if lang in d:
                return d[lang]
    return _(d['en'])


def convert_source(source, lang):
    return SourceSelection(
        name=_translate(source.name, lang),
        description=_translate(source.description, lang),
        id=source.id,
        size=source.size,
        variant=source.variant,
        default=source.default)


class SourceController(SubiquityController):

    model_name = "source"

    endpoint = API.source

    def start(self):
        path = '/cdrom/casper/install-sources.yaml'
        if self.app.opts.source_catalog is not None:
            path = self.app.opts.source_catalog
        if not os.path.exists(path):
            return
        with open(path) as fp:
            self.model.load_from_file(fp)

    def interactive(self):
        if len(self.model.sources) <= 1:
            return False
        return super().interactive()

    async def GET(self) -> SourceSelectionAndSetting:
        cur_lang = self.app.base_model.locale.selected_language
        cur_lang = cur_lang.rsplit('.', 1)[0]

        return SourceSelectionAndSetting(
            [
                convert_source(source, cur_lang)
                for source in self.model.sources
            ],
            self.model.current.id)

    def configured(self):
        super().configured()
        self.app.base_model.set_source_variant(self.model.current.variant)

    async def POST(self, source_id: str) -> None:
        for source in self.model.sources:
            if source.id == source_id:
                self.model.current = source
        self.configured()
