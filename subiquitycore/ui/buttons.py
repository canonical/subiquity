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

from urwid import Button, Text
from functools import partial


class PlainButton(Button):
    button_left = Text("[")
    button_right = Text("]")


class MenuSelectButton(Button):
    button_left = Text("")
    button_right = Text(">")


start_btn = partial(PlainButton, label="Start", on_press=None)
confirm_btn = partial(PlainButton, label="Confirm", on_press=None)
cancel_btn = partial(PlainButton, label="Cancel", on_press=None)
done_btn = partial(PlainButton, label="Done", on_press=None)
finish_btn = partial(PlainButton, label="Finish", on_press=None)
ok_btn = partial(PlainButton, label="OK", on_press=None)
continue_btn = partial(PlainButton, label="Continue", on_press=None)
reset_btn = partial(PlainButton, label="Reset", on_press=None)
menu_btn = partial(MenuSelectButton, on_press=None)
