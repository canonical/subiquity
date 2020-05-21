# Copyright 2015 Canonical, Ltd.
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

from subiquitycore import i18n


log = logging.getLogger('subiquity.models.locale')


class LocaleModel(object):
    """ Model representing locale selection

    XXX Only represents *language* selection for now.
    """

    selected_language = None

    def get_languages(self, is_linux_tty):
        base = os.environ.get("SNAP", ".")
        lang_path = os.path.join(base, "languagelist")

        languages = []
        with open(lang_path) as lang_file:
            for line in lang_file:
                level, code, name = line.strip().split(':')
                if is_linux_tty and level != "console":
                    continue
                languages.append((code, name))
        languages.sort(key=lambda x: x[1])
        return languages

    def switch_language(self, code):
        self.selected_language = code
        i18n.switch_language(code)

    def __repr__(self):
        return "<Selected: {}>".format(self.selected_language)
