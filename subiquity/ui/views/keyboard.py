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

from urwid import (
    connect_signal,
    Text,
    )

from subiquitycore.ui.container import (
    ListBox,
    Pile,
    )
from subiquitycore.ui.form import (
    Form,
    FormField,
    )
from subiquitycore.ui.selector import Option, Selector
from subiquitycore.ui.utils import Padding
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.ui.views.keyboard")


class ChoiceField(FormField):

    def __init__(self, caption=None, help=None, choices=[]):
        super().__init__(caption, help)
        self.choices = choices

    def _make_widget(self, form):
        return Selector(self.choices)

class KeyboardForm(Form):

    layout = ChoiceField(_("Layout"), choices=["dummy"])
    variant = ChoiceField(_("Variant"), choices=["dummy"])


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
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)
        connect_signal(self.form.layout.widget, "select", self.select_layout)
        self.form.layout.widget._options = opts
        self.form.layout.widget.value = us_keyboard

        self._rows = self.form.as_rows(self)
        pile = Pile([
            ('pack', Text("")),
            Padding.center_90(ListBox([self._rows])),
            ('pack', Pile([
                Text(""),
                self.form.buttons,
                Text(""),
                ])),
            ])
        pile.focus_position = 2
        super().__init__(pile)

    def done(self, result):
        self.controller.done()

    def cancel(self, result):
        self.controller.cancel()

    def select_layout(self, sender, keyboard):
        log.debug("%s", keyboard)
        opts = []
        for code, desc in keyboard.variants:
            opts.append(Option((desc, True, code)))
        opts.sort(key=lambda o:o.label)
        opts.insert(0, Option(("default", True, None)))
        self.form.variant.widget._options = opts
        self.form.variant.widget.index = 0
        self.form.variant.enabled = len(opts) > 1



