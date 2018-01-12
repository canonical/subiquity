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

from subiquity.ui.views import pc105

log = logging.getLogger("subiquity.ui.views.keyboard")


class AutoDetectBase(WidgetWrap):
    def __init__(self, keyboard_detector, step):
        self.keyboard_detector = keyboard_detector
        self.step = step
        lb = LineBox(self.make_body(), "Keyboard auto-detection")
        super().__init__(lb)
    def start(self):
        pass
    def stop(self):
        pass
    def keypress(self, size, key):
        if key == 'esc':
            self.keyboard_detector.backup()
        else:
            return super().keypress(size, key)


class AutoDetectIntro(AutoDetectBase):

    def ok(self, sender):
        self.keyboard_detector.do_step(0)

    def cancel(self, sender):
        self.keyboard_detector.abort()

    def make_body(self):
        return Pile([
                Text("Keyboard detection starting. You will be asked a series of questions about your keyboard. Press escape at any time to go back to the previous screen."),
                Text(""),
                button_pile([
                    ok_btn(label="OK", on_press=self.ok),
                    ok_btn(label="Cancel", on_press=self.cancel),
                    ]),
                ])


class AutoDetectFailed(AutoDetectBase):

    def ok(self, sender):
        self.keyboard_detector.abort()

    def make_body(self):
        return Pile([
                Text("Keybaord auto detection failed, sorry"),
                Text(""),
                button_pile([ok_btn(label="OK", on_press=self.ok)]),
                ])

class AutoDetectResult(AutoDetectBase):

    preamble = """\
Keyboard auto detection completed.

Your keyboard was detected as:
"""
    postamble = """\

If this is correct, select Done on the next screen. If not you can select \
another layout or run the automated detection again.

"""

    def ok(self, sender):
        self.keyboard_detector.keyboard_view.found_layout(self.step.result)

    def make_body(self):
        model = self.keyboard_detector.keyboard_view.model
        layout, variant = model.lookup(self.step.result)
        var_desc = []
        if variant is not None:
            var_desc = [Text("    Variant: " + variant.desc)]
        return Pile([
                Text(self.preamble),
                Text("    Layout: " + layout.desc),
            ] + var_desc + [
                Text(self.postamble),
                button_pile([ok_btn(label="OK", on_press=self.ok)]),
                ])


class AutoDetectPressKey(AutoDetectBase):

    def selectable(self):
        return True

    def make_body(self):
        return Pile([
            Text(_("Please press one of the following keys:")),
            Text(""),
            Columns([Text(s, align="center") for s in self.step.symbols], dividechars=1),
            Text(""),
            ])

    @property
    def input_filter(self):
        return self.keyboard_detector.keyboard_view.controller.input_filter

    def start(self):
        self.input_filter.enter_keycodes_mode()

    def stop(self):
        self.input_filter.exit_keycodes_mode()

    def keypress(self, size, key):
        log.debug('keypress %r %r', size, key)
        if key.startswith('release '):
            # Escape is key 1 on keyboards and all layouts except
            # amigas and very old Macs so this seems safe enough.
            if key == 'release 1':
                return super().keypress(size, 'esc')
            else:
                return
        elif key.startswith('press '):
            code = int(key[len('press '):])
            if code not in self.step.keycodes:
                return
            v = self.step.keycodes[code]
        else:
            # If we're not on a linux tty, the filtering won't have
            # happened and so there's no way to get the keycodes. Do
            # something literally random instead.
            import random
            v = random.choice(list(self.step.keycodes.values()))
        self.keyboard_detector.do_step(v)


class AutoDetectKeyPresent(AutoDetectBase):

    def yes(self, sender):
        self.keyboard_detector.do_step(self.step.yes)

    def no(self, sender):
        self.keyboard_detector.do_step(self.step.no)

    def make_body(self):
        return Pile([
            Text("Is the following key present on your keyboard?"),
            Text(""),
            Text(self.step.symbol, align="center"),
            Text(""),
            button_pile([
                ok_btn(label="Yes", on_press=self.yes),
                other_btn(label="No", on_press=self.no),
                ]),
            ])

class Detector:

    def __init__(self, kview):
        self.keyboard_view = kview
        self.pc105tree = pc105.PC105Tree()
        self.pc105tree.read_steps()
        self.seen_steps = []

    def start(self):
        o = AutoDetectIntro(self, None)
        self.keyboard_view.show_overlay(o)

    def abort(self):
        overlay = self.keyboard_view._w.top_w
        overlay.stop()
        self.keyboard_view.remove_overlay()

    step_cls_to_view_cls = {
        pc105.StepResult: AutoDetectResult,
        pc105.StepPressKey: AutoDetectPressKey,
        pc105.StepKeyPresent: AutoDetectKeyPresent,
        }

    def backup(self):
        if len(self.seen_steps) == 0:
            self.seen_steps = []
            self.abort()
            return
        if len(self.seen_steps) == 1:
            self.seen_steps = []
            self.abort()
            self.start()
            return
        self.seen_steps.pop()
        step_index = self.seen_steps.pop()
        self.do_step(step_index)

    def do_step(self, step_index):
        self.abort()

        log.debug("moving to step %s", step_index)
        try:
            step = self.pc105tree.steps[step_index]
        except KeyError:
            view = AutoDetectFailed(self, None)
        else:
            self.seen_steps.append(step_index)
            log.debug("step: %s", repr(step))
            view = self.step_cls_to_view_cls[type(step)](self, step)

        view.start()
        self.keyboard_view.show_overlay(view)


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


class KeyboardView(BaseView):
    def __init__(self, model, controller, opts):
        self.model = model
        self.controller = controller
        self.opts = opts

        self.form = KeyboardForm()
        opts = []
        cur_layout = None
        cur_variant = None
        for layout in model.layouts:
            if layout.code == model.layout:
                cur_layout = layout
                for variant  in layout.variants:
                    if variant.code == model.variant:
                        cur_variant = variant
            opts.append(Option((layout.desc, True, layout)))
        opts.sort(key=lambda o:o.label)
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)
        connect_signal(self.form.layout.widget, "select", self.select_layout)
        self.form.layout.widget._options = opts
        self.form.layout.widget.value = cur_layout
        self.form.variant.widget.value = cur_variant

        self._rows = self.form.as_rows(self)
        identify_btn = other_btn(label=_("Identify keyboard"), on_press=self.detect)
        lb = ListBox([self._rows, Text(""), button_pile([identify_btn])])
        pile = Pile([
            ('pack', Text("")),
            Padding.center_90(lb),
            ('pack', Pile([
                Text(""),
                self.form.buttons,
                Text(""),
                ])),
            ])
        lb._select_last_selectable()
        pile.focus_position = 2
        super().__init__(pile)

    def detect(self, sender):
        detector = Detector(self)
        detector.start()

    def found_layout(self, result):
        self.remove_overlay()
        log.debug("found_layout %s", result)
        layout, variant = self.model.lookup(result)
        self.form.layout.widget.value = layout
        self.form.variant.widget.value = variant
        self._w.focus_position = 2

    def done(self, result):
        layout = self.form.layout.widget.value.code
        variant = ''
        if self.form.variant.widget.value is not None:
            variant = self.form.variant.widget.value.code
        self.controller.done(layout, variant)

    def cancel(self, result=None):
        self.controller.cancel()

    def select_layout(self, sender, layout):
        log.debug("%s", layout)
        opts = []
        for variant in layout.variants:
            opts.append(Option((variant.desc, True, variant)))
        opts.sort(key=lambda o:o.label)
        opts.insert(0, Option(("default", True, None)))
        self.form.variant.widget._options = opts
        self.form.variant.widget.index = 0
        self.form.variant.enabled = len(opts) > 1
