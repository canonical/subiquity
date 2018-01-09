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
    LineBox,
    Text,
    WidgetWrap,
    )

from subiquitycore.ui.buttons import ok_btn, other_btn
from subiquitycore.ui.container import (
    Columns,
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


class AutoDetectBase(WidgetWrap):
    def __init__(self, *args):
        lb = LineBox(self.make_body(*args), "Keyboard auto-detection")
        super().__init__(lb)
    def start(self):
        pass
    def stop(self):
        pass

class AutoDetectIntro(AutoDetectBase):
    def make_body(self, cb):
        return Pile([
                Text("Auto detection beginning"),
                Text(""),
                button_pile([ok_btn(label="OK", on_press=lambda sender: cb(0))]),
                ])

class AutoDetectFailed(AutoDetectBase):
    def make_body(self, cb):
        return Pile([
                Text("Keybaord auto detection failed, sorry"),
                Text(""),
                button_pile([ok_btn(label="OK", on_press=lambda sender: cb())]),
                ])

class AutoDetectComplete(AutoDetectBase):
    def make_body(self, cb, result, view):
        variant = None
        kb_var = None
        model = result
        if ':' in result:
            model, variant = result.split(":", 1)
        log.debug("%s %s", model, variant)
        for kb in view.model.keyboards:
            if kb.code == model:
                if variant is None:
                    break
                for v in kb.variants:
                    if v[0] == variant:
                        kb_var = v[1]
                break
        else:
            xxx
        view.form.layout.widget.value = kb
        view.form.variant.widget.value = variant
        var_desc = []
        if kb_var is not None:
            var_desc = [Text("    Variant: " + kb_var)]
        return Pile([
                Text("Keyboard auto detection completed"),
                Text(""),
                Text("Your keyboard was detected as:"),
                Text(""),
                Text("    Layout: " + kb.desc),
            ] + var_desc + [
                Text(""),
                Text("If this is correct, select Done on the next screen. If not you can select another layout or run the automated detection again."),
                Text(""),
                button_pile([ok_btn(label="OK", on_press=lambda sender: cb(kb))]),
                ])

class AutoDetectPressKey(AutoDetectBase):
    def selectable(self):
        return True
    def __init__(self, input_filter, *args):
        self.input_filter = input_filter
        log.debug("? %r", args)
        super().__init__(*args)
    def make_body(self, cb, symbols, keycodes):
        self.keycodes = keycodes
        self.cb = cb
        return Pile([
            Text("press one of these"),
            Text(""),
            Columns([Text(s) for s in symbols], dividechars=1),
            ])
    def start(self):
        self.input_filter.start_filtering()
    def stop(self):
        self.input_filter.stop_filtering()
    def keypress(self, size, key):
        log.debug('keypress %r %r', size, key)
        if key.startswith('release '):
            return
        elif key.startswith('press '):
            code = int(key[len('press '):])
            if code not in self.keycodes:
                return
            v = self.keycodes[code]
        else:
            import random
            v = random.choice(list(self.keycodes.values()))
        self.cb(v)

class AutoDetectKeyPresent(AutoDetectBase):
    def make_body(self, cb, symbols, yes, no):
        self.cb = cb
        return Pile([
            Text("Is the following key present on your keyboard?"),
            Text(""),
            Columns([Text(s) for s in symbols], dividechars=1),
            button_pile([
                ok_btn(label="Yes", on_press=lambda sender: cb(yes)),
                other_btn(label="No", on_press=lambda sender: cb(no)),
                ]),
            ])

class Detector:

    def __init__(self, kview):
        self.keyboard_view = kview
        self.keyboard_detector = KeyboardDetector()

    def start(self):
        o = AutoDetectIntro(self._do_step)
        self.keyboard_view.show_overlay(o)

    def abort(self):
        overlay = self.keyboard_view._w.top_w
        overlay.stop()
        self.keyboard_view.remove_overlay()

    def _do_step(self, result):
        self.abort()
        try:
            r = self.keyboard_detector.read_step(result)
        except Exception:
            o = AutoDetectFailed(self.abort)
        else:
            if r == KeyboardDetector.RESULT:
                log.debug("RESULT %r", self.keyboard_detector.result)
                o = AutoDetectComplete(
                    self.keyboard_view.found_keyboard,
                    self.keyboard_detector.result,
                    self.keyboard_view)
            elif r == KeyboardDetector.PRESS_KEY:
                log.debug("PRESS_KEY %r %r", self.keyboard_detector.symbols, self.keyboard_detector.keycodes)
                o = AutoDetectPressKey(
                    self.keyboard_view.controller.input_filter,
                    self._do_step,
                    self.keyboard_detector.symbols,
                    self.keyboard_detector.keycodes)
            elif r == KeyboardDetector.KEY_PRESENT or r == KeyboardDetector.KEY_PRESENT_P:
                log.debug("PRESENT %r", self.keyboard_detector.symbols)
                o = AutoDetectKeyPresent(
                    self._do_step,
                    self.keyboard_detector.symbols,
                    self.keyboard_detector.present,
                    self.keyboard_detector.not_present,
                    )
            else:
                o = AutoDetectFailed(self.abort)
        o.start()
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

    def found_keyboard(self, result):
        self.remove_overlay()
        log.debug("found_keyboard %s", result)
        self._w.focus_position = 2

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



