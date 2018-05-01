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
import os
from subiquitycore import i18n

log = logging.getLogger('subiquity.models.locale')

class LocaleModel(object):
    """ Model representing locale selection

    XXX Only represents *language* selection for now.
    """

    supported_languages = [
        ('en_US', 'English'),
        ('ast_ES', 'Asturian'),
        ('ca_EN', 'Catalan'),
        ('hr_HR', 'Croatian'),
        ('nl_NL', 'Dutch'),
        ('fi_FI', 'Finnish'),
        ('fr_FR', 'French'),
        ('de_DE', 'German'),
        ('el_GR', 'Greek, Modern (1453-)'),
#        ('he_IL', 'Hebrew'), # disabled as it does not render correctly on a vt with default font
        ('hu_HU', 'Hungarian'),
        ('lv_LV', 'Latvian'),
        ('nb_NO', 'Norsk bokmål'), # iso_639_3 for nb does not translate Norwgian
        ('pl_PL', 'Polish'),
        ('ru_RU', 'Russian'),
        ('es_ES', 'Spanish'),
        ('uk_UA', 'Ukrainian'),
    ]
    selected_language = None

    def __init__(self, signal):
        self.signal = signal
        lang = os.environ.get("LANG")
        if lang.endswith(".UTF-8"):
            lang = lang.rsplit('.', 1)[0]
        for code, name in self.supported_languages:
            if code == lang:
                self.switch_language(code)

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
