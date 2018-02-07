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

log = logging.getLogger('subiquity.models.locale')

class LocaleModel(object):
    """ Model representing locale selection

    XXX Only represents *language* selection for now.
    """

    def __init__(self, signal):
        self.signal = signal

    supported_languages = [
        ('en_US', 'English'),
        ('ca_EN', 'Catalan'),
        ('hu_HU', 'Hungarian'),
        ('lv_LV', 'Latvian'),
        ('ru_RU', 'Russian'),
    ]

    selected_language = None

    def get_languages(self):
        languages = []
        for code, name in self.supported_languages:
            native = name
            if gettext.find('iso_639_3', languages=[code]):
                native_lang = gettext.translation('iso_639_3', languages=[code])
                native = native_lang.gettext(name).capitalize()
            languages.append((code, native))
        return languages

    def switch_language(self, code):
        self.selected_language = code
        self.signal.emit_signal('l10n:language-selected', code)
        i18n.switch_language(code)

    def __repr__(self):
        return "<Selected: {}>".format(self.selected_language)
