# Copyright 2020 Canonical, Ltd.
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

from subiquity.common.serialize import Serializer
from subiquity.common.types import (
    KeyboardLayout,
    )


class KeyboardList:

    def __init__(self):
        self._kbnames_dir = os.path.join(os.environ.get("SNAP", '.'), 'kbds')
        self.serializer = Serializer(compact=True)
        self._clear()

    def _file_for_lang(self, code):
        return os.path.join(self._kbnames_dir, code + '.jsonl')

    def has_language(self, code):
        return os.path.exists(self._file_for_lang(code))

    def load_language(self, code):
        if code == self.current_lang:
            return

        self._clear()

        with open(self._file_for_lang(code)) as kbdnames:
            self.layouts = [
                self.serializer.from_json(KeyboardLayout, line)
                for line in kbdnames
                ]
        self.current_lang = code

    def _clear(self):
        self.current_lang = None
        self.layouts = []
