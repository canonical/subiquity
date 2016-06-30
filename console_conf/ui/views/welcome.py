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

""" Welcome

Welcome provides user with language selection

"""
import logging
from urwid import Pile
from subiquitycore.ui.buttons import start_btn
from subiquitycore.ui.utils import Color
from subiquitycore.ui.views.welcome import CoreWelcomeView

log = logging.getLogger("console_conf.views.welcome")


class WelcomeView(CoreWelcomeView):
    def _build_buttons(self):
        self.buttons = [
            Color.button(start_btn(on_press=self.confirm),
                         focus_map='button focus'),
        ]
        return Pile(self.buttons)

    def confirm(self, result):
        self.model.selected_language = result.label
        log.debug('calling network')
        self.signal.emit_signal('menu:network:main')
