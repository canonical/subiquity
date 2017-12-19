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
from urwid import Text
from subiquitycore.ui.lists import SimpleList
from subiquitycore.ui.buttons import forward_btn
from subiquitycore.ui.container import Pile
from subiquitycore.ui.utils import Padding
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.views.welcome")


class WelcomeView(BaseView):

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        super().__init__(Pile([
            ('pack', Text("")),
            Padding.center_50(self._build_model_inputs()),
            ('pack', Text("")),
            ]))

    def _build_model_inputs(self):
        sl = []
        for code, native in self.model.get_languages():
            sl.append(forward_btn(label=native, on_press=self.confirm, user_arg=code))

        return SimpleList(sl)

    def confirm(self, sender, code):
        self.model.switch_language(code)
        log.debug('calling installpath')
        self.controller.done()
