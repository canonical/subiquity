# Copyright 2021 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
from subiquity.server.controllers.locale import LocaleController

log = logging.getLogger('system_setup.server.controllers.locale')


class WSLLocaleController(LocaleController):
    def start(self):
        if self.app.prefillInfo:
            welcome = self.app.prefillInfo.get('Welcome', {'lang': None})
            win_lang = welcome.get('lang')
            if win_lang:
                self.model.selected_language = win_lang
                log.debug('Prefilled Language: {}'
                          .format(self.model.selected_language))

        super().start()
