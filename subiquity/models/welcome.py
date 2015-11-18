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

    supported_languages = ['English',
                           'Belgian',
                           'French',
                           'German',
                           'Italian']
    selected_language = None

    def get_signals(self):
        return self.signals

    def get_menu(self):
        return self.supported_languages

    def get_signal_by_name(self, selection):
        for x, y, z in self.get_menu():
            if x == selection:
                return y

    def __repr__(self):
        if self.selected_language is 'French':
            language = gettext.translation(domain='subiquity', localedir='/home/kick/work/subiquity/locale',
                                           languages=[os.environ['fr']],fallback=True)
            language.install()
        else:
            language = gettext.translation(domain='subiquity', localedir='/home/kick/work/subiquity/locale',
                                           languages=[os.environ['en']],fallback=True)
            language.install()
        return "<Selected: {}>".format(self.selected_language)
