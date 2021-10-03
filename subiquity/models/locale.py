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

from subiquitycore.utils import split_cmd_output

log = logging.getLogger('subiquity.models.locale')


class LocaleModel:
    """ Model representing locale selection

    XXX Only represents *language* selection for now.
    """

    selected_language = None
    locale_support = "locale-only"

    def __init__(self, chroot_prefix):
        self.chroot_prefix = chroot_prefix

    def switch_language(self, code):
        self.selected_language = code

    def __repr__(self):
        return "<Selected: {}>".format(self.selected_language)

    def make_cloudconfig(self):
        if not self.selected_language:
            return {}
        if self.locale_support == "none":
            return {}
        locale = self.selected_language
        if '.' not in locale and '_' in locale:
            locale += '.UTF-8'
        return {'locale': locale}

    async def target_packages(self):
        if self.selected_language is None:
            return []
        if self.locale_support != "langpack":
            return []
        lang = self.selected_language.split('.')[0]
        if lang == "C":
            return []

        return await split_cmd_output(
            self.chroot_prefix + ['check-language-support', '-l', lang], None)
