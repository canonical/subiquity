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

from subiquitycore.ui.buttons import ok_btn
from subiquitycore.ui.container import ListBox, Pile
from subiquitycore.ui.utils import button_pile
from subiquitycore.view import BaseView

log = logging.getLogger("console_conf.views.welcome")


class WelcomeView(BaseView):
    def __init__(self, controller):
        self.controller = controller
        super().__init__(Pile([
            # need to have a listbox or something else "stretchy" here or
            # urwid complains.
            ListBox([Text('')]),
            ('pack', button_pile([ok_btn("OK", on_press=self.confirm)])),
            ('pack', Text("")),
            ], focus_item=1))

    def confirm(self, result):
        self.controller.done()
