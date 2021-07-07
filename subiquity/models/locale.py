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

log = logging.getLogger('subiquity.models.locale')


class LocaleModel(object):
    """ Model representing locale selection

    XXX Only represents *language* selection for now.
    """

    selected_language = 'C'

    def switch_language(self, code):
        self.selected_language = code

    def __repr__(self):
        return "<Selected: {}>".format(self.selected_language)

    def make_cloudconfig(self):
        if not self.selected_language or self.selected_language == 'C':
            return {}
        locale = self.selected_language
        if '.' not in locale and '_' in locale:
            locale += '.UTF-8'
        return {'locale': locale}
