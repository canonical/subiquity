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
    WidgetWrap,
    )

from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.container import (
    ListBox,
    Pile,
    )
from subiquitycore.ui.form import (
    Form,
    FormField,
    )
from subiquitycore.ui.selector import Option, Selector
from subiquitycore.ui.utils import button_pile, Padding
from subiquitycore.view import BaseView

from subiquity.ui.views.keyboard_detector import KeyboardDetector

log = logging.getLogger("subiquity.ui.views.keyboard")


class ChoiceField(FormField):

    def __init__(self, caption=None, help=None, choices=[]):
        super().__init__(caption, help)
        self.choices = choices

    def _make_widget(self, form):
        return Selector(self.choices)

class KeyboardForm(Form):

    cancel_label = _("Back")

    layout = ChoiceField(_("Layout:"), choices=["dummy"])
    variant = ChoiceField(_("Variant:"), choices=["dummy"])


class AutoDetectIntro(WidgetWrap):
    def __init__(self, cb):
        super().__init__(other_btn(label="OK", on_press=lambda sender: cb(0)))

class Detector:

    def __init__(self, kview):
        self.keyboard_view = kview
        self.keyboard_detector = KeyboardDetector()

    def start(self):
        o = AutoDetectIntro(self._do_step)
        self.keyboard_view.show_overlay(o)

    def _do_step(self, result):
        self.keyboard_view.remove_overlay()
        try:
            r = self.keyboard_detector.read_step(result)
        except Exception:
            o = AutoDetectionFailed(self.keyboard_view)
        else:
            if r == KeyboardDetector.RESULT:
                self.keyboard_view.found_keyboard(self.keyboard_detector.result)
                return
            elif r == KeyboardDetector.PRESS_KEY:
                o = AutoDetectPressKey(self._do_step, self.keyboard_detector.symbols, self.keyboard_detector.keycodes)
            elif r == KeyboardDetector.KEY_PRESENT or r == KeyboardDetector.KEY_PRESENT_P:
                o = AutoDetectKeyPresent(self._do_step, self.keyboard_detector.symbols)
            else:
                o = AutoDetectionFailed(self.keyboard_view)
        self.keyboard_view.show_overlay(o)


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
        identify_btn = other_btn(label=_("Identify keyboard"), on_press=self.detect)
        pile = Pile([
            ('pack', Text("")),
            Padding.center_90(ListBox([self._rows, Text(""), button_pile([identify_btn])])),
            ('pack', Pile([
                Text(""),
                self.form.buttons,
                Text(""),
                ])),
            ])
        pile.focus_position = 2
        super().__init__(pile)

    def detect(self, sender):
        detector = Detector(self)
        detector.start()

    def done(self, result):
        self.controller.done()

    def cancel(self, result=None):
        self.controller.cancel()

    def select_layout(self, sender, keyboard):
        log.debug("%s", keyboard)
        opts = []
        for code, desc, langs in keyboard.variants:
            opts.append(Option((desc, True, code)))
        opts.sort(key=lambda o:o.label)
        opts.insert(0, Option(("default", True, None)))
        self.form.variant.widget._options = opts
        self.form.variant.widget.index = 0
        self.form.variant.enabled = len(opts) > 1



