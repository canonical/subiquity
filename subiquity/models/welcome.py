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
import gettext
import gzip
from subiquity.model import ModelPolicy


log = logging.getLogger('subiquity.welcome')


class WelcomeModel(ModelPolicy):
    """ Model representing language selection
    """
    prev_signal = None

    signals = [
        ("Welcome view",
         'menu:welcome:main',
         'welcome')
    ]

    supported_languages = { 
                            'French': ('fr','Français'),
                            'English': ('en','English'),
                            'Spanish': ('es','Español'),
                            'Chinese (Simplified)': ('zh','中文(简体)'),
                            'Portuguese': ('pt','Português'),
                            'German': ('de','Deutsch'),
                            'Italian': ('it','Italiano'),
                            'Russian': ('ru','Русский'),
                            'Additional': ('other','languages'),
    }

    selected_language = None

#    def __init__(self):
#        self._build_language_list()

    def _read_language_datafile(self):
       return [l.strip('\n') for l in gzip.open('locale/languagelist.data.gz', 'rt')]

    def full_language_list(self):
        for lang in self._read_language_datafile():
            num, shortname, langname, displayname = lang.split(':') 
            self.supported_languages[langname] = (shortname, displayname)
#        self.supported_languages = [ "{} [{}]".format(l.split(":")[2],l.split(":")[3]) 
#                                     for l in self._read_language_datafile()]

    def get_signals(self):
        return self.signals

    def get_menu(self):
        return [ "{}-[{}]".format(key, value[1]) 
                 for key, value in sorted(self.supported_languages.items()) ]

    def get_signal_by_name(self, selection):
        for x, y, z in self.get_menu():
            if x == selection:
                return y

    def set_language(self, language):
        shortLanguage = language.split('-')[0]
        self.selected_language = { shortLanguage: self.supported_languages[shortLanguage] }
        if shortLanguage is "C":
            language = gettext.translation(domain='subiquity', languages=['en'], 
                                           fallback=True)
            language.install()
            log.info('welcome: No localization')
        else:
            for trans, value in self.supported_languages.items():
                if trans == shortLanguage:
                    language = gettext.translation(domain='subiquity', languages=[value[0]], 
                                                   fallback=True)
                    language.install()
                    log.info('welcome: chosen loacalization: {}'.format(self.selected_language))
                    break

    def get_language(self):
        return self.selected_language

    def __repr__(self):
        return "<Selected: {}>".format(self.selected_language)
