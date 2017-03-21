# Copyright 2017 Canonical, Ltd.
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

from urwid import (
    AttrMap,
    connect_signal,
    delegate_to_widget_mixin,
    emit_signal,
    MetaSignals,
    Text,
    WidgetDecoration,
    WidgetDisable,
    WidgetWrap,
    )

from subiquitycore.ui.buttons import cancel_btn, done_btn
from subiquitycore.ui.container import Columns, Pile
from subiquitycore.ui.interactive import (
    Help,
    PasswordEditor,
    IntegerEditor,
    StringEditor,
    )
from subiquitycore.ui.utils import Color

class Toggleable(delegate_to_widget_mixin('_original_widget'), WidgetDecoration):

    def __init__(self, original, active_color):
        self.original = original
        self.active_color = active_color
        self.enabled = False
        self.enable()

    def enable(self):
        if not self.enabled:
            self.original_widget = AttrMap(self.original, self.active_color, self.active_color + ' focus')
            self.enabled = True

    def disable(self):
        if self.enabled:
            self.original_widget = WidgetDisable(Color.info_minor(self.original))
            self.enabled = False

class _Validator(WidgetWrap):

    def __init__(self, field, w):
        self.field = field
        super().__init__(w)

    def lost_focus(self):
        self.field.validate()


class FormField(object):

    next_index = 0

    def __init__(self, caption=None, cleaner=None, validator=None, help=None):
        self.caption = caption
        self.cleaner = cleaner
        self.validator = validator
        self.help = help
        self.index = FormField.next_index
        FormField.next_index += 1

    def _make_widget(self, form):
        raise NotImplementedError(self._make_widget)

    def bind(self, form):
        widget = self._make_widget(form)
        return BoundFormField(self, form, widget)

    def clean(self, value):
        if self.cleaner is not None:
            return self.cleaner(value)
        else:
            return value

    def validate(self, value):
        pass


class BoundFormField(object):

    def __init__(self, field, form, widget):
        self.field = field
        self.form = form
        self.in_error = False
        self._help = None
        self._caption = None
        self.pile = None
        self._enabled = True
        self.showing_extra = False
        self.widget = widget

    def clean(self, value):
        value = self.field.clean(value)
        cleaner = getattr(self.form, "clean_" + self.field.name, None)
        if cleaner is not None:
            value = cleaner(value)
        return value

    def _validate(self):
        if not self._enabled:
            return
        try:
            v = self.value
        except ValueError as e:
            return str(e)
        if self.field.validator is not None:
            r = self.field.validator(v)
            if r is not None:
                return r
        validator = getattr(self.form, "validate_" + self.field.name, None)
        if validator is not None:
            return validator()

    def validate(self):
        self.hide_extra()
        r = self._validate()
        if r is None:
            self.in_error = False
        else:
            self.in_error = True
            extra = Color.info_error(Text(r, align="center"))
            self.show_extra(extra)
        self.form.validated()

    def hide_extra(self):
        if self.showing_extra:
            del self.pile.contents[1]
            self.showing_extra = False

    def show_extra(self, extra):
        t = (extra, self.pile.options('pack'))
        if self.showing_extra:
            self.pile.contents[1] = t
        else:
            self.pile.contents[1:1] = [t]
        self.showing_extra = True

    @property
    def value(self):
        return self.clean(self.widget.value)

    @value.setter
    def value(self, val):
        self.widget.value = val

    @property
    def help(self):
        if self._help is not None:
            return self._help
        else:
            return self.field.help

    @help.setter
    def help(self, val):
        self._help = val

    @property
    def caption(self):
        if self._caption is not None:
            return self._caption
        else:
            return self.field.caption

    @caption.setter
    def caption(self, val):
        self._caption = val

    def _cols(self):
        text = Text(self.caption, align="right")
        if self._enabled:
            input = Color.string_input(_Validator(self, self.widget))
        else:
            input = self.widget
        if self.help is not None:
            help = Help(self.parent_view, self.help)
        else:
            help = Text("")
        cols = [
                    (self._longest_caption, text),
                    input,
                    (3, help),
                ]
        cols = Columns(cols, dividechars=2)
        if self._enabled:
            return cols
        else:
            return WidgetDisable(Color.info_minor(cols))

    def as_row(self, view, longest_caption):
        if self.pile is not None:
            raise RuntimeError("do not call as_row more than once!")
        self.parent_view = view
        self._longest_caption = longest_caption
        self.pile = Pile([self._cols()])
        return self.pile

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, val):
        if val != self._enabled:
            self._enabled = val
            if self.pile is not None:
                self.pile.contents[0] = (self._cols(), self.pile.contents[0][1])


def simple_field(widget_maker):
    class Field(FormField):
        def _make_widget(self, form):
            return widget_maker()
    return Field


StringField = simple_field(StringEditor)
PasswordField = simple_field(PasswordEditor)
IntegerField = simple_field(IntegerEditor)

class MetaForm(MetaSignals):

    def __init__(self, name, bases, attrs):
        super().__init__(name, bases, attrs)
        _unbound_fields = []
        for k, v in attrs.items():
            if isinstance(v, FormField):
                v.name = k
                if v.caption is None:
                    v.caption = k + ":"
                _unbound_fields.append(v)
        _unbound_fields.sort(key=lambda f:f.index)
        self._unbound_fields = _unbound_fields


class Form(object, metaclass=MetaForm):

    signals = ['submit', 'cancel']

    opts = {}

    def __init__(self):
        self.done_btn = Toggleable(done_btn(), 'button')
        self.cancel_btn = Toggleable(cancel_btn(), 'button')
        connect_signal(self.done_btn.base_widget, 'click', self._click_done)
        connect_signal(self.cancel_btn.base_widget, 'click', self._click_cancel)
        self.buttons = Pile([self.done_btn, self.cancel_btn])
        self._fields = []
        for field in self._unbound_fields:
            bf = field.bind(self)
            setattr(self, bf.field.name, bf)
            self._fields.append(bf)

    def _click_done(self, sender):
        emit_signal(self, 'submit', self)

    def _click_cancel(self, sender):
        emit_signal(self, 'cancel', self)

    def remove_field(self, field_name):
        new_fields = []
        for bf in self._fields:
            if bf.field.name != field_name:
                new_fields.append(bf)
        self._fields[:] = new_fields

    @property
    def longest_caption(self):
        longest_caption = 0
        for field in self._fields:
            longest_caption = max(longest_caption, len(field.caption))
        return longest_caption

    def as_rows(self, view):
        longest_caption = self.longest_caption
        rows = []
        for field in self._fields:
            rows.append(field.as_row(view, longest_caption))
        return Pile(rows)

    def validated(self):
        in_error = False
        for f in self._fields:
            if f.in_error:
                in_error = True
                break
        if in_error:
            self.buttons.contents[0][0].disable()
            self.buttons.focus_position = 1
        else:
            self.buttons.contents[0][0].enable()
