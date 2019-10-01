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


def _stylized_button(left, right, style):
    class Btn(Button):
        button_left = Text(left)
        button_right = Text(right)

    class StyleAttrMap(AttrMap):
        def __init__(self, label, on_press=None, user_arg=None):
            btn = Btn(label, on_press=on_press, user_data=user_arg)
            btn._w.contents[2] = (
                btn._w.contents[2][0],
                btn._w.options('given', len(right)))
            super().__init__(btn, style + '_button', style + '_button focus')
    return StyleAttrMap


def action_button(style):
    return _stylized_button('[', ']', style)


_forward_rhs = "\N{BLACK RIGHT-POINTING SMALL TRIANGLE} ]"

menu_btn = _stylized_button("[", _forward_rhs, "menu")
forward_btn = _stylized_button("[", _forward_rhs, "done")

header_btn = action_button("frame")
done_btn = action_button("done")
danger_btn = action_button("danger")
other_btn = action_button("other")

ok_btn = done_btn

delete_btn = danger_btn

back_btn = other_btn
cancel_btn = other_btn
reset_btn = other_btn
