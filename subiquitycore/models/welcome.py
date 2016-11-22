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
from subiquitycore.model import BaseModel


log = logging.getLogger('subiquitycore.welcome')


class WelcomeModel(BaseModel):
    """ Model representing language selection
    """
    prev_signal = None

    supported_languages = ['English',
                           'Belgian',
                           'German',
                           'Italian']
    selected_language = None

    def get_menu(self):
        return self.supported_languages

    def __repr__(self):
        return "<Selected: {}>".format(self.selected_language)
