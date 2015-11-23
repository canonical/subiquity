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

    supported_languages = []

    selected_language = None

    def get_signals(self):
        return self.signals

    def get_menu(self):
        filelist = gzip.open('locale/languagelist.data.gz','rt')
        languageList = []
        for lang in filelist:
            lang = lang.strip('\n')
            self.supported_languages.append(lang)
            lang = lang.split(':')
            languageList.append(lang[2] + ' [' + lang[3] + ']')
        return languageList

    def get_signal_by_name(self, selection):
        for x, y, z in self.get_menu():
            if x == selection:
                return y

    def set_language(self, language):
        shortLanguage = language.split(' ')[0]
        self.selected_lanquage = shortLanguage
        log.info("Selected language: {}".format(shortLanguage))
        if shortLanguage is "C":
            language = gettext.translation(domain='subiquity', languages=['en'], 
                                           fallback=True)
            language.install()
        else:
            for trans in self.supported_languages:
                trans = trans.split(":")
                if trans[2] == shortLanguage:
                    language = gettext.translation(domain='subiquity', languages=[trans[1]], 
                                                   fallback=True)
                    language.install()
                    break

    def get_language(self):
        return self.selected_language

    def __repr__(self):
        return "<Selected: {}>".format(self.selected_language)
