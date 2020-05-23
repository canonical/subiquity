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
    ACTIVATE,
    AttrWrap,
    CompositeCanvas,
    connect_signal,
    LineBox,
    Padding as UrwidPadding,
    PopUpLauncher,
    Text,
    )

from subiquitycore.ui.container import (
    Columns,
    ListBox,
    WidgetWrap,
    )
from subiquitycore.ui.utils import (
    Color,
    )
from subiquitycore.ui.width import widget_width


class ClickableThing(WidgetWrap):
    signals = ['click']

    def selectable(self):
        return True

    def render(self, size, focus=False):
        c = super().render(size, focus)
        if focus:
            # create a new canvas so we can add a cursor
            c = CompositeCanvas(c)
            c.cursor = self.get_cursor_coords(size)
        return c

    def get_cursor_coords(self, size):
        """
        Return the position of the cursor if visible.  This method
        is required for widgets that display a cursor.
        """
        return 0, 0

    def move_cursor_to_coords(self, size, x, y):
        return True

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        self._emit('click')


class _PopUpSelectDialog(WidgetWrap):
    """A list of PopUpButtons with a box around them."""

    def __init__(self, parent, cur_index):
        self.parent = parent
        group = []
        for i, option in enumerate(self.parent._options):
            if option.enabled:
                btn = ClickableThing(option.label)
                connect_signal(btn, 'click', self.click, i)
                if i == cur_index:
                    rhs = '\N{BLACK LEFT-POINTING SMALL TRIANGLE} '
                else:
                    rhs = ''
            else:
                btn = option.label
                rhs = ''
            row = Columns([
                (1, Text("")),
                btn,
                (2, Text(rhs)),
                ])
            if option.enabled:
                row = AttrWrap(row, 'menu_button', 'menu_button focus')
            else:
                row = AttrWrap(row, 'info_minor')
            btn = UrwidPadding(row, width=self.parent._padding.width)
            group.append(btn)
        list_box = ListBox(group)
        list_box.base_widget.focus_position = cur_index
        super().__init__(Color.body(LineBox(list_box)))

    def click(self, btn, index):
        self.parent.index = index
        self.parent.close_pop_up()

    def keypress(self, size, key):
        if key == 'esc':
            self.parent.close_pop_up()
        else:
            return super().keypress(size, key)


class SelectorError(Exception):
    pass


class Option:

    def __init__(self, val):
        if not isinstance(val, tuple):
            if isinstance(val, Option):
                self.label = val.label
                self.enabled = val.enabled
                self.value = val.value
            elif isinstance(val, str):
                self.label = val
                self.enabled = True
                self.value = val
            else:
                raise SelectorError("invalid option %r", val)
        elif len(val) == 1:
            self.label = val[0]
            self.enabled = True
            self.value = val[0]
        elif len(val) == 2:
            self.label = val[0]
            self.enabled = val[1]
            self.value = val[0]
        elif len(val) == 3:
            self.label = val[0]
            self.enabled = val[1]
            self.value = val[2]
        else:
            raise SelectorError("invalid option %r", val)
        if isinstance(self.label, str):
            self.label = Text(_(self.label))


class _Launcher(PopUpLauncher):
    # PopUpLauncher is a WidgetDecoration, which means base_widget
    # steps past it. This means that if Selector just inherited from
    # PopUpLauncher, calling .base_widget on a (say) Padding
    # containing a Selector would return the SelectableIcon, not the
    # Selector. This is unhelpful, to put it mildly, so we do some
    # proxying about so that PopUpLauncher can inherit from WidgetWrap
    # instead.
    def __init__(self, parent, child):
        self.parent = parent
        super().__init__(child)

    def create_pop_up(self):
        return self.parent.create_pop_up()

    def get_pop_up_parameters(self):
        return self.parent.get_pop_up_parameters()


class Selector(WidgetWrap):
    """A widget that allows the user to chose between options by popping
       up a list of options.

    (A bit like <select> in an HTML form).
    """

    signals = ['select']

    def __init__(self, opts, index=0):
        self._icon = ClickableThing(Text(""))
        self._padding = UrwidPadding(AttrWrap(
            Columns([
                (1, Text('[')),
                self._icon,
                (3, Text('\N{BLACK DOWN-POINTING SMALL TRIANGLE} ]')),
                ], dividechars=1),
            'menu_button', 'menu_button focus'))

        options = []
        for opt in opts:
            options.append(Option(opt))

        self.options = options
        self._set_index(index)
        super().__init__(_Launcher(self, self._padding))

    def get_natural_width(self):
        return self._padding.width

    def keypress(self, size, key):
        if self._command_map[key] != ACTIVATE:
            return key
        self.open_pop_up()

    def _set_index(self, val):
        self._icon._w = self._options[val].label
        self._index = val

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, val):
        self._emit('select', self._options[val].value)
        self._set_index(val)

    @property
    def options(self):
        return self._options[:]

    @options.setter
    def options(self, val):
        self._options = val
        self._padding.width = max(
            [widget_width(o.label) for o in self._options]) + 6

    def option_by_label(self, label):
        for opt in self._options:
            if opt.label == label:
                return opt

    def option_by_value(self, value):
        for opt in self._options:
            if opt.value == value:
                return opt

    def option_by_index(self, index):
        return self._options[index]

    @property
    def value(self):
        return self._options[self._index].value

    @value.setter
    def value(self, val):
        for i, opt in enumerate(self._options):
            if opt.value == val:
                self._set_index(i)
                return
        raise AttributeError("cannot set value to %r", val)

    def create_pop_up(self):
        return _PopUpSelectDialog(self, self.index)

    def get_pop_up_parameters(self):
        # line on left, space, line on right
        return {'left': 0, 'top': -self.index - 1,
                'overlay_width': self._padding.width,
                'overlay_height': len(self._options) + 2}

    def open_pop_up(self):
        self._w.open_pop_up()

    def close_pop_up(self):
        self._w.close_pop_up()
