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

from functools import partial

from urwid import AttrWrap, Button, connect_signal, Text

class PlainButton(Button):
    button_left = Text("[")
    button_right = Text("]")


class MenuSelectButton(Button):
    button_left = Text("")
    button_right = Text(">")


def plain_btn(label, color, on_press=None, user_arg=None):
    button = PlainButton(label=label)
    if on_press is not None:
        connect_signal(button, 'click', on_press, user_arg)
    return AttrWrap(button, color, color + ' focus')


start_btn = partial(plain_btn, "Start", "save_button")
save_btn = partial(plain_btn, "Save", "save_button")
finish_btn = partial(plain_btn, "Finish", "save_button")
ok_btn = partial(plain_btn, "OK", "save_button")
confirm_btn = partial(plain_btn, "Confirm", "save_button")
done_btn = partial(plain_btn, "Done", "save_button")
continue_btn = partial(plain_btn, "Continue", "save_button")

reset_btn = partial(plain_btn, "Reset", "reset_button")

cancel_btn = partial(plain_btn, "Cancel", "cancel_button")
back_btn = partial(plain_btn, "Back", "cancel_button")

danger_btn = partial(plain_btn, color="danger_button")

def menu_btn(label, on_press=None, user_arg=None):
    button = MenuSelectButton(label=label)
    if on_press is not None:
        connect_signal(button, 'click', on_press, user_arg)
    return AttrWrap(button, 'menu_button', 'menu_button focus')
