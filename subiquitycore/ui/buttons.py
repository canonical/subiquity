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

from subiquitycore.ui.utils import Color

class PlainButton(Button):
    button_left = Text("[")
    button_right = Text("]")


class MenuSelectButton(Button):
    button_left = Text("")
    button_right = Text(">")


def start_btn(label="Start"):
    return Color.save_button(PlainButton(label=label))

def cancel_btn(label="Cancel"):
    return Color.cancel_button(PlainButton(label=label))

def save_btn(label="Save"):
    return Color.save_button(PlainButton(label=label))

def finish_btn(label="Finish"):
    return save_btn(label)

def ok_btn(label="OK"):
    return save_btn(label)

def confirm_btn(label="Confirm"):
    return save_btn(label)

def done_btn(label="Done"):
    return save_btn(label)

def continue_btn(label="Continue"):
    return save_btn(label)

def reset_btn(label="Reset"):
    return Color.reset_button(PlainButton(label=label))

def menu_btn(label):
    return Color.menu_button(MenuSelectButton(label=label))
