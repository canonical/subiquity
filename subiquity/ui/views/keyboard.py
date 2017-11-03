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
import re

from urwid import (
    connect_signal,
    )

from subiquitycore.ui.container import (
    ListBox,
    )
from subiquitycore.ui.form import (
    Form,
    FormField,
    )
from subiquitycore.ui.selector import Option, Selector
from subiquitycore.ui.utils import button_pile, Padding
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.ui.views.keyboard")


class ChoiceField(FormField):

    def __init__(self, caption=None, help=None, choices=[]):
        super().__init__(caption, help)
        self.choices = choices

    def _make_widget(self, form):
        return Selector(self.choices)

class KeyboardForm(Form):

    layout = ChoiceField(choices=["dummy"])
    variant = ChoiceField(choices=["dummy"])


class KeyboardView(BaseView):
    def __init__(self, model, controller, opts):
        self.model = model
        self.controller = controller
        self.opts = opts

        self.form = KeyboardForm()
        opts = []
        us_keyboard = None
        for keyboard in model.keyboards:
            if keyboard.code == "us":
                us_keyboard = keyboard
            opts.append(Option((keyboard.desc, True, keyboard)))
        opts.sort(key=lambda o:o.label)
        self.form.layout.widget._options = opts
        self.form.layout.widget.value = us_keyboard
        connect_signal(self.form, 'submit', self.done)

        body = [
            Padding.center_90(self.form.as_rows(self)),
            Padding.line_break(""),
            self.form.buttons,
        ]
        super().__init__(ListBox(body))

    def done(self, result):
        pass


