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

import gettext
import logging
from subiquitycore import i18n

log = logging.getLogger('subiquity.models.welcome')


class WelcomeModel(object):
    """ Model representing language selection
    """

    supported_languages = [('en_US', 'English'), ('ru_RU', 'Russian')]
    selected_language = None

    def get_languages(self):
        languages = []
        for code, name in self.supported_languages:
            label = name
            native = name
            if gettext.find('iso_639_3'):
                cur_lang = gettext.translation('iso_639_3')
                label = cur_lang.gettext(name).capitalize()
            if gettext.find('iso_639_3', languages=[code]):
                native_lang = gettext.translation('iso_639_3', languages=[code])
                native = native_lang.gettext(name).capitalize()
            languages.append((code, label, native))
        return languages

    def switch_language(self, code):
        self.selected_language = code
        i18n.switch_language(code)

    def __repr__(self):
        return "<Selected: {}>".format(self.selected_language)
