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
from subiquitycore.controller import BaseController
from subiquitycore.models import LocaleModel
from subiquitycore.ui.views import LocaleView

log = logging.getLogger('subiquitycore.controllers.locale')


class CoreLocaleController(BaseController):

    _view = LocaleView

    def __init__(self, common):
        super().__init__(common)
        self.model = LocaleModel(self.opts)

    def locale(self):
        title = "Language setup"
        excerpt = ("Please select your keyboard model:")
        footer = ""
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 40)
        self.ui.set_body(self.view(self.model, self.signal))

