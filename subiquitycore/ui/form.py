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

import abc
import logging
from urllib.parse import urlparse

from urwid import (
    CheckBox,
    connect_signal,
    delegate_to_widget_mixin,
    emit_signal,
    MetaSignals,
    Padding as UrwidPadding,
    RadioButton,
    Text,
    WidgetDecoration,
    )

from subiquitycore.ui.buttons import cancel_btn, done_btn
from subiquitycore.ui.container import (
    Pile,
    WidgetWrap,
)
from subiquitycore.ui.interactive import (
    PasswordEditor,
    IntegerEditor,
    StringEditor,
    EmailEditor,
    )
from subiquitycore.ui.selector import Selector
from subiquitycore.ui.table import (
    ColSpec,
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    button_pile,
    Color,
    disabled,
    screen,
    )
from subiquitycore.ui.width import (
    widget_width,
    )


log = logging.getLogger("subiquitycore.ui.form")


# Passing NO_CAPTION as the caption of a field supresses the caption
# entirely so the field occupies the full width of the form.
NO_CAPTION = object()

# Passing NO_HELP as the help of a field supresses the gap under a
# field where the help would go. This means there is nowhere to put
# validation failures, so don't use this on fields that have any
# validation at all.
NO_HELP = object()


class Toggleable(delegate_to_widget_mixin('_original_widget'),
                 WidgetDecoration):

    has_original_width = True

    def __init__(self, original):
        self.original = original
        self._enabled = False
        self.enabled = True

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, val):
        if val and not self._enabled:
            self.original_widget = self.original
        elif not val and self._enabled:
            self.original_widget = disabled(self.original)
        self._enabled = val


class _Validator(WidgetWrap):

    def __init__(self, field, w):
        self.field = field
        super().__init__(w)

    def get_natural_width(self):
        return widget_width(self._w)

    def lost_focus(self):
        self.field.showing_extra = False
        lf = getattr(self._w.base_widget, 'lost_focus', None)
        if lf is not None:
            lf()
        self.field.validate()


class FormField(abc.ABC):

    next_index = 0
    takes_default_style = True
    caption_first = True

    def __init__(self, caption=None, help=None):
        self.caption = caption
        self.help = help
        self.index = FormField.next_index
        FormField.next_index += 1

    @abc.abstractmethod
    def _make_widget(self, form):
        pass

    def bind(self, form):
        widget = self._make_widget(form)
        return BoundFormField(self, form, widget)


class WantsToKnowFormField(object):
    """A marker class."""
    def set_bound_form_field(self, bff):
        self.bff = bff


form_colspecs = {1: ColSpec(pack=False)}


class BoundFormField(object):

    def __init__(self, field, form, widget):
        self.field = field
        self.form = form
        self.widget = widget

        self.in_error = False
        self._enabled = True
        self._help = None
        self.showing_extra = False

        self._build_table()

        if 'change' in getattr(widget, 'signals', []):
            connect_signal(widget, 'change', self._change)
        if isinstance(widget, WantsToKnowFormField):
            widget.set_bound_form_field(self)

    def _build_table(self):
        widget = self.widget
        if self.field.takes_default_style:
            widget = Color.string_input(widget)

        if self.help is not NO_HELP:
            self.under_text = Text(self.help)
        else:
            self.under_text = Text("")
        if self.field.caption is NO_CAPTION:
            first_row = [(2, _Validator(self, widget))]
            second_row = [(2, self.under_text)]
        else:
            self.caption_text = Text(_(self.field.caption))

            if self.field.caption_first:
                self.caption_text.align = 'right'
                first_row = [self.caption_text, _Validator(self, widget)]
            else:
                first_row = [
                    _Validator(
                        self,
                        UrwidPadding(
                            widget, align='right',
                            width=widget_width(widget))),
                    self.caption_text,
                    ]
            second_row = [Text(""), self.under_text]

        rows = [first_row]
        if self.help is not NO_HELP:
            rows.append(second_row)

        self._rows = [Toggleable(TableRow(row)) for row in rows]

        self._table = TablePile(self._rows, spacing=2, colspecs=form_colspecs)

    def clean(self, value):
        cleaner = getattr(self.form, "clean_" + self.field.name, None)
        if cleaner is not None:
            value = cleaner(value)
        return value

    def _change(self, sender, new_val):
        if self.in_error or self.showing_extra:
            self.showing_extra = False
            # the validator will likely inspect self.value to decide
            # if the new input is valid. So self.value had better
            # return the new value and we stuff it into tmpval to do
            # this. It's a bit of a hack but oh well...
            self.tmpval = new_val
            r = self._validate()
            del self.tmpval
            if r is not None:
                return
            self.in_error = False
            if not self.showing_extra and self.help is not NO_HELP:
                self.under_text.set_text(self.help)
            self.form.validated()

    def _validate(self):
        if not self._enabled:
            return
        try:
            self.value
        except ValueError as e:
            return str(e)
        validator = getattr(self.form, "validate_" + self.field.name, None)
        if validator is not None:
            return validator()

    def validate(self, show_error=True):
        # cleaning/validation can call show_extra to add an
        # informative message. We record this by having show_extra to
        # set showing_extra so we don't immediately replace this
        # message with the widget's help in the case that validation
        # succeeds.
        r = self._validate()
        if r is None:
            self.in_error = False
            if not self.showing_extra and self.help is not NO_HELP:
                self.under_text.set_text(self.help)
        else:
            self.in_error = True
            if show_error:
                self.show_extra(('info_error', r))
        self.form.validated()

    def show_extra(self, extra_markup):
        self.showing_extra = True
        self.under_text.set_text(extra_markup)

    @property
    def value(self):
        return self.clean(getattr(self, 'tmpval', self.widget.value))

    @value.setter
    def value(self, val):
        self.widget.value = val

    @property
    def help(self):
        if self._help is not None:
            return self._help
        elif self.field.help is not None:
            if isinstance(self.field.help, str):
                return _(self.field.help)
            else:
                return self.field.help
        else:
            return ""

    @help.setter
    def help(self, val):
        if val is None:
            val = ""
        self._help = val
        self.under_text.set_text(val)

    @property
    def caption(self):
        return self.caption_text.text

    @caption.setter
    def caption(self, val):
        self.caption_text.set_text(val)

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, val):
        self._enabled = val
        for row in self._rows:
            row.enabled = val


def simple_field(widget_maker):
    class Field(FormField):
        def _make_widget(self, form):
            return widget_maker()
    return Field


StringField = simple_field(StringEditor)
PasswordField = simple_field(PasswordEditor)
IntegerField = simple_field(IntegerEditor)
EmailField = simple_field(EmailEditor)


class RadioButtonEditor(RadioButton):

    reserve_columns = 3

    @property
    def value(self):
        return self.state

    @value.setter
    def value(self, val):
        self.state = val


class RadioButtonField(FormField):

    caption_first = False
    takes_default_style = False

    def __init__(self, group, caption=None, help=None):
        if group is None:
            group = []
        group.append(self)
        self.group = group
        super().__init__(caption, help)

    def _make_widget(self, form):
        for bf in form._fields:
            if bf.field in self.group:
                group = bf.widget.group
                break
        else:
            group = []
        return RadioButtonEditor(group, "")


class URLEditor(StringEditor, WantsToKnowFormField):
    def __init__(self, allowed_schemes=frozenset(['http', 'https'])):
        self.allowed_schemes = allowed_schemes
        super().__init__()

    @StringEditor.value.getter
    def value(self):
        v = self.get_edit_text()
        if v == "":
            return v
        parsed = urlparse(v)
        if parsed.scheme not in self.allowed_schemes:
            schemes = []
            for s in sorted(self.allowed_schemes):
                schemes.append(s)
            if len(schemes) > 2:
                schemes = ", ".join(schemes[:-1]) + _(", or ") + schemes[-1]
            elif len(schemes) == 2:
                schemes = schemes[0] + _(" or ") + schemes[1]
            else:
                schemes = schemes[0]
            raise ValueError(
                _("This field must be a {schemes} URL.").format(
                    schemes=schemes))
        return v


URLField = simple_field(URLEditor)


class ChoiceField(FormField):

    takes_default_style = False

    def __init__(self, caption=None, help=None, choices=[]):
        super().__init__(caption, help)
        self.choices = choices

    def _make_widget(self, form):
        return Selector(self.choices)


class ReadOnlyWidget(Text):

    @property
    def value(self):
        return self.text

    @value.setter
    def value(self, val):
        self.set_text(val)


class ReadOnlyField(FormField):

    takes_default_style = False

    def _make_widget(self, form):
        return ReadOnlyWidget("")


class CheckBoxEditor(CheckBox):

    reserve_columns = 3

    @property
    def value(self):
        return self.state

    @value.setter
    def value(self, val):
        self.state = val


class BooleanField(FormField):

    caption_first = False
    takes_default_style = False

    def _make_widget(self, form):
        return CheckBoxEditor('')


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
        _unbound_fields.sort(key=lambda f: f.index)
        self._unbound_fields = _unbound_fields


class Form(object, metaclass=MetaForm):

    signals = ['submit', 'cancel']

    ok_label = _("Done")
    cancel_label = _("Cancel")

    def __init__(self, initial={}):
        self.done_btn = Toggleable(done_btn(_(self.ok_label),
                                   on_press=self._click_done))
        self.cancel_btn = Toggleable(cancel_btn(_(self.cancel_label),
                                     on_press=self._click_cancel))
        self.buttons = button_pile([self.done_btn, self.cancel_btn])
        self._fields = []
        for field in self._unbound_fields:
            bf = field.bind(self)
            setattr(self, bf.field.name, bf)
            self._fields.append(bf)
            if field.name in initial:
                bf.value = initial[field.name]
        for bf in self._fields:
            bf.validate(show_error=False)
        self.validated()

    def enter_data(self, data):
        for bf in self._fields:
            if bf.field.name in data:
                bf.field.value = data[bf.field.name]

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

    def as_rows(self):
        if len(self._fields) == 0:
            return []
        t0 = self._fields[0]._table
        rows = [t0]
        for field in self._fields[1:]:
            rows.append(Text(""))
            t = field._table
            t0.bind(t)
            rows.append(t)
        return rows

    def as_screen(self, focus_buttons=True, excerpt=None, narrow_rows=False):
        return screen(
            self.as_rows(), self.buttons,
            focus_buttons=focus_buttons, excerpt=excerpt,
            narrow_rows=narrow_rows)

    def validated(self):
        in_error = False
        for f in self._fields:
            if f.in_error:
                in_error = True
                break
        if in_error:
            self.buttons.base_widget.contents[0][0].enabled = False
            self.buttons.base_widget.focus_position = 1
        else:
            self.buttons.base_widget.contents[0][0].enabled = True

    def as_data(self):
        data = {}
        for field in self._fields:
            if field.enabled:
                data[field.field.name] = field.value
        return data


class SubFormWidget(WidgetWrap):

    def __init__(self, form):
        self.form = form
        super().__init__(Pile(form.as_rows()))

    @property
    def value(self):
        return self.form.as_data()

    @value.setter
    def value(self, data):
        for k, v in data.items():
            getattr(self.form, k).value = v


class SubFormField(FormField):

    takes_default_style = False

    def __init__(self, form_cls, caption=None, help=None):
        super().__init__(caption=caption, help=help)
        self.form_cls = form_cls

    def _make_widget(self, form):
        form = self.form_cls(form)
        return SubFormWidget(form)


class SubForm(Form):

    def __init__(self, parent, **kw):
        self.parent = parent
        super().__init__(**kw)
