# Copyright 2019 Canonical, Ltd.
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
    Divider,
    PopUpLauncher,
    SolidFill,
    Text,
    )

from subiquitycore.ui.buttons import (
    header_btn,
    )
from subiquitycore.ui.container import (
    Columns,
    ListBox,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.utils import (
    ClickableIcon,
    Color,
    )
from subiquitycore.ui.width import (
    widget_width,
    )


log = logging.getLogger('subiquity.ui.help')

tlcorner = '┌'
tline = '─'
lline = '│'
trcorner = '┐'
blcorner = '└'
rline = '│'
bline = '─'
brcorner = '┘'


def menu_item(text):
    return Color.frame_button(ClickableIcon(_(text), 0))


class HelpMenu(WidgetWrap):

    def __init__(self, parent):
        self.parent = parent
        close = header_btn(_("Help"))
        top = Columns([
            ('fixed', 1, Text(tlcorner)),
            Divider(tline),
            (widget_width(close), close),
            ('fixed', 1, Text(trcorner)),
            ])
        about = menu_item(_("About the installer"))
        local = menu_item(_("Help on this screen"))
        keys = menu_item(_("Help on keyboard shortcuts"))
        entries = [
            about,
            local,
            Divider(tline),
            keys,
            ]
        buttons = [
            close,
            about,
            local,
            keys,
            ]
        for button in buttons:
            connect_signal(button.base_widget, 'click', self._close)
        middle = Columns([
            ('fixed', 1, SolidFill(lline)),
            ListBox(entries),
            ('fixed', 1, SolidFill(rline)),
            ])
        bottom = Columns([
            (1, Text(blcorner)),
            Divider(bline),
            (1, Text(brcorner)),
            ])
        self.width = max([widget_width(b) for b in buttons]) + 2
        self.height = len(entries) + 2
        super().__init__(Color.frame_header(Pile([
            ('pack', top),
            middle,
            ('pack', bottom),
            ])))

    def _close(self, sender):
        self.parent.close_pop_up()


class HelpButton(PopUpLauncher):

    def __init__(self, app):
        self.app = app
        self.btn = header_btn(_("Help"), on_press=self._open)
        super().__init__(self.btn)

    def _open(self, sender):
        log.debug("open help menu")
        self.open_pop_up()

    def create_pop_up(self):
        self._menu = HelpMenu(self)
        return self._menu

    def get_pop_up_parameters(self):
        return {
            'left': widget_width(self.btn) - self._menu.width + 1,
            'top': 0,
            'overlay_width': self._menu.width,
            'overlay_height': self._menu.height,
            }
