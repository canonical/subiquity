# Copyright 2018 Canonical, Ltd.
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

import locale
import logging

from urwid import (
    connect_signal,
    LineBox,
    Text,
    Padding as UrwidPadding
    )

from subiquitycore.ui.buttons import (
    cancel_btn,
    ok_btn,
    other_btn,
    )
from subiquitycore.ui.container import (
    Columns,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.form import (
    ChoiceField,
    Form,
    )
from subiquitycore.ui.selector import Selector, Option
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.stretchy import (
    Stretchy,
    )
from subiquitycore.ui.utils import button_pile, Color, Padding, screen
from subiquitycore.view import BaseView

from subiquity.client.keyboard import for_ui, latinizable
from subiquity.common.types import (
    KeyboardSetting,
    StepKeyPresent,
    StepPressKey,
    StepResult,
    )

log = logging.getLogger("subiquity.ui.views.keyboard")


class AutoDetectBase(WidgetWrap):
    def __init__(self, keyboard_detector, step):
        self.keyboard_detector = keyboard_detector
        self.step = step
        lb = LineBox(
            Pile([
                ('pack', Text("")),
                ('pack', UrwidPadding(self.make_body(), left=2, right=2)),
                ('pack', Text(""))
            ]),
            _("Keyboard auto-detection"))
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
        self.keyboard_detector.do_step("0")

    def cancel(self, sender):
        self.keyboard_detector.abort()

    def make_body(self):
        return Pile([
                Text(_("Keyboard detection starting. You will be asked a "
                       "series of questions about your keyboard. Press escape "
                       "at any time to go back to the previous screen.")),
                Text(""),
                button_pile([
                    ok_btn(label=_("OK"), on_press=self.ok),
                    ok_btn(label=_("Cancel"), on_press=self.cancel),
                    ]),
                ])


class AutoDetectResult(AutoDetectBase):

    preamble = _("""\
Keyboard auto detection completed.

Your keyboard was detected as:
""")
    postamble = _("""\

If this is correct, select Done on the next screen. If not you can select \
another layout or run the automated detection again.

""")

    @property
    def _kview(self):
        return self.keyboard_detector.keyboard_view

    def ok(self, sender):
        self._kview.found_layout(self.layout, self.variant)

    def make_body(self):
        self.layout, self.variant = self._kview.lookup(
            self.step.layout, self.step.variant)
        layout_text = _("Layout")
        var_text = _("Variant")
        width = max(len(layout_text), len(var_text), 12)
        return Pile([
                Text(_(self.preamble)),
                Text("%*s: %s" % (width, layout_text, self.layout.name)),
                Text("%*s: %s" % (width, var_text, self.variant.name)),
                Text(_(self.postamble)),
                button_pile([ok_btn(label=_("OK"), on_press=self.ok)]),
                ])


class AutoDetectPressKey(AutoDetectBase):
    # This is the tricky case. We need access to the "keycodes" not
    # the characters that the current keyboard set up maps the
    # keycodes to. The heavy lifting is done by the InputFilter class
    # in subiquitycore.core.

    def selectable(self):
        return True

    def make_body(self):
        self.error_text = Text("", align="center")
        self.pile = Pile([
            ('pack', Text(_("Please press one of the following keys:"))),
            ('pack', Text("")),
            ('pack', Columns([Text(s, align="center")
                              for s in self.step.symbols], dividechars=1)),
            ])
        return self.pile

    @property
    def input_filter(self):
        return self.keyboard_detector.keyboard_view.controller.app.input_filter

    def start(self):
        self.input_filter.enter_keycodes_mode()

    def stop(self):
        self.input_filter.exit_keycodes_mode()

    def error(self, message):
        t = Color.info_error(Text(message, align='center'))
        self.pile.contents.extend([
            (Text(""), self.pile.options('pack')),
            (t,        self.pile.options('pack')),
            ])

    def keypress(self, size, key):
        log.debug('keypress %r', key)
        if key.startswith('release '):
            # Escape is key 1 on all keyboards and all layouts except
            # amigas and very old Macs so this seems safe enough.
            if key == 'release 1':
                return super().keypress(size, 'esc')
            else:
                return
        elif key.startswith('press '):
            code = int(key[len('press '):])
            if code not in self.step.keycodes:
                self.error(_("Input was not recognized, try again"))
                return
            v = self.step.keycodes[code]
        else:
            # If we're not on a linux tty, the filtering won't have
            # happened and so there's no way to get the keycodes. Do
            # something literally random instead.
            if key == 'e':
                self.error(_("Input was not recognized, try again"))
                return
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
            Text(_("Is the following key present on your keyboard?")),
            Text(""),
            Text(self.step.symbol, align="center"),
            Text(""),
            button_pile([
                ok_btn(label=_("Yes"), on_press=self.yes),
                other_btn(label=_("No"), on_press=self.no),
                ]),
            ])


class Detector:
    # Encapsulates the state of the autodetection process.

    def __init__(self, kview):
        self.keyboard_view = kview
        self.pc105_steps = kview.keyboard_list.load_pc105()
        self.seen_steps = []

    def start(self):
        self.overlay = AutoDetectIntro(self, None)
        self.keyboard_view.show_overlay(self.overlay)

    def abort(self):
        self.overlay.stop()
        self.keyboard_view.remove_overlay()

    step_cls_to_view_cls = {
        StepResult: AutoDetectResult,
        StepPressKey: AutoDetectPressKey,
        StepKeyPresent: AutoDetectKeyPresent,
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
        step = self.pc105_steps[step_index]
        self.seen_steps.append(step_index)
        log.debug("step: %s", repr(step))
        self.overlay = self.step_cls_to_view_cls[type(step)](self, step)

        self.overlay.start()
        self.keyboard_view.show_overlay(self.overlay)


class ApplyingConfig(WidgetWrap):
    def __init__(self, aio_loop):
        spinner = Spinner(aio_loop, style='dots')
        spinner.start()
        text = _("Applying config")
        # | text |
        # 12    34
        self.width = len(text) + 4
        super().__init__(
            LineBox(
                Pile([
                    ('pack', Text(' ' + text)),
                    ('pack', spinner),
                    ])))


toggle_text = _("""\
You will need a way to toggle the keyboard between the national layout and \
the standard Latin layout.

Right Alt or Caps Lock keys are often chosen for ergonomic reasons (in the \
latter case, use the combination Shift+Caps Lock for normal Caps toggle). \
Alt+Shift is also a popular combination; it will however lose its usual \
behavior in Emacs and other programs that use it for specific needs.

Not all listed keys are present on all keyboards. """)


toggle_options = [
    (_('Caps Lock'),               True, 'caps_toggle'),
    (_('Right Alt (AltGr)'),       True, 'toggle'),
    (_('Right Control'),           True, 'rctrl_toggle'),
    (_('Right Shift'),             True, 'rshift_toggle'),
    (_('Right Logo key'),          True, 'rwin_toggle'),
    (_('Menu key'),                True, 'menu_toggle'),
    (_('Alt+Shift'),               True, 'alt_shift_toggle'),
    (_('Control+Shift'),           True, 'ctrl_shift_toggle'),
    (_('Control+Alt'),             True, 'ctrl_alt_toggle'),
    (_('Alt+Caps Lock'),           True, 'alt_caps_toggle'),
    (_('Left Control+Left Shift'), True, 'lctrl_lshift_toggle'),
    (_('Left Alt'),                True, 'lalt_toggle'),
    (_('Left Control'),            True, 'lctrl_toggle'),
    (_('Left Shift'),              True, 'lshift_toggle'),
    (_('Left Logo key'),           True, 'lwin_toggle'),
    (_('Scroll Lock key'),         True, 'sclk_toggle'),
    (_('No toggling'),             True, None),
    ]


class ToggleQuestion(Stretchy):

    def __init__(self, parent, setting):
        self.parent = parent
        self.setting = setting
        self.selector = Selector(toggle_options)
        self.selector.value = 'alt_shift_toggle'
        if self.parent.initial_setting.toggle:
            try:
                self.selector.value = self.parent.initial_setting.toggle
            except AttributeError:
                pass

        widgets = [
            Text(_(toggle_text)),
            Text(""),
            Padding.center_79(Columns([
                ('pack', Text(_("Shortcut: "))),
                self.selector,
                ])),
            Text(""),
            button_pile([
                ok_btn(label=_("OK"), on_press=self.ok),
                cancel_btn(label=_("Cancel"), on_press=self.cancel),
                ]),
            ]
        super().__init__(
            _("Select layout toggle"),
            widgets,
            stretchy_index=0,
            focus_index=4)

    def ok(self, sender):
        self.parent.remove_overlay()
        self.setting.toggle = self.selector.value
        self.parent.really_done(self.setting)

    def cancel(self, sender):
        self.parent.remove_overlay()


class KeyboardForm(Form):

    cancel_label = _("Back")

    layout = ChoiceField(_("Layout:"), choices=["dummy"])
    variant = ChoiceField(_("Variant:"), choices=["dummy"])


class KeyboardView(BaseView):

    title = _("Keyboard configuration")

    def __init__(self, controller, initial_setting):
        self.controller = controller
        self.keyboard_list = controller.keyboard_list
        self.initial_setting = initial_setting

        self.form = KeyboardForm()
        opts = []
        for layout in self.keyboard_list.layouts:
            opts.append(Option((layout.name, True, layout)))
        opts.sort(key=lambda o: locale.strxfrm(o.label.text))
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)
        connect_signal(self.form.layout.widget, "select", self.select_layout)
        self.form.layout.widget.options = opts
        setting = for_ui(initial_setting)
        layout, variant = self.lookup(setting.layout, setting.variant)
        self.set_values(layout, variant)

        if self.controller.opts.run_on_serial:
            excerpt = _('Please select the layout of the keyboard directly '
                        'attached to the system, if any.')
        else:
            excerpt = _('Please select your keyboard layout below, or select '
                        '"Identify keyboard" to detect your layout '
                        'automatically.')

        lb_contents = self.form.as_rows()
        if not self.controller.opts.run_on_serial:
            lb_contents.extend([
                Text(""),
                button_pile([
                    other_btn(label=_("Identify keyboard"),
                              on_press=self.detect)]),
                ])
        super().__init__(screen(
            lb_contents,
            self.form.buttons,
            excerpt=excerpt,
            narrow_rows=True))

    def detect(self, sender):
        Detector(self).start()

    def found_layout(self, layout, variant):
        self.remove_overlay()
        log.debug("found_layout %r %r", layout.code, variant.code)
        self.set_values(layout, variant)
        self._w.base_widget.focus_position = 4

    def done(self, result):
        data = result.as_data()
        layout = data['layout']
        variant = data.get('variant', layout.variants[0])
        setting = KeyboardSetting(layout=layout.code, variant=variant.code)
        other = latinizable(setting)
        if setting != other:
            self.show_stretchy_overlay(ToggleQuestion(self, other))
        else:
            self.really_done(setting)

    def really_done(self, setting):
        apply = False
        if setting != self.initial_setting:
            apply = True
            ac = ApplyingConfig(self.controller.app.aio_loop)
            self.show_overlay(ac, width=ac.width, min_width=None)
        self.controller.done(setting, apply=apply)

    def cancel(self, result=None):
        self.controller.cancel()

    def select_layout(self, sender, layout):
        if sender is not None:
            log.debug("select_layout %s", layout)
        opts = []
        for variant in layout.variants:
            opts.append(Option((variant.name, True, variant)))
        # ./scripts/make-kbd-info.py checks that the default is always
        # at index 0
        opts[1:] = sorted(opts[1:], key=lambda o: locale.strxfrm(o.label.text))
        self.form.variant.widget.options = opts
        self.form.variant.widget.index = 0
        self.form.variant.enabled = len(opts) > 1

    def lookup(self, layout_code, variant_code):
        for layout in self.keyboard_list.layouts:
            if layout.code == layout_code:
                break
            if layout.code == "us":
                default = layout
        else:
            layout = default
        for variant in layout.variants:
            if variant.code == variant_code:
                return layout, variant
        return layout, layout.variants[0]

    def set_values(self, layout, variant):
        self.form.layout.widget.value = layout
        self.select_layout(None, layout)
        self.form.variant.widget.value = variant
