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

from urwid import AttrMap, Button, Text

def _stylized_button(left, right, stocklabel, style):
    class Btn(Button):
        button_left = Text(left)
        button_right = Text(right)

    class StyleAttrMap(AttrMap):
        def __init__(self, *args, **kwargs):
            label = kwargs.pop('label', _(stocklabel))
            btn = Btn(label, *args, **kwargs)
            super().__init__(btn, style + '_button', style + '_button focus')
    return StyleAttrMap

def stylized_button(stocklabel, style):
    return _stylized_button('[', ']', stocklabel, style)

def menu_btn(label, on_press=None, user_arg=None):
    MenuBtn=_stylized_button('', '>', label, 'menu')
    return MenuBtn(on_press=on_press, user_data=user_arg)

ok_btn = stylized_button("OK", "save")
done_btn = stylized_button("Done", "save")

reset_btn = stylized_button("Reset", "reset")

cancel_btn = stylized_button("Cancel", "cancel")
close_btn = stylized_button("Close", "cancel")

danger_btn = stylized_button("Continue", "danger")
delete_btn = stylized_button("Delete", "danger")
