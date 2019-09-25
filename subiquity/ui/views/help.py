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
    Filler,
    PopUpLauncher,
    Text,
    )

from subiquitycore.ui.buttons import (
    header_btn,
    )
from subiquitycore.ui.container import (
    Columns,
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


hline = Divider('─')
vline = Text('│')
tlcorner = Text('┌')
trcorner = Text('┐')
blcorner = Text('└')
brcorner = Text('┘')
rtee = Text('┤')
ltee = Text('├')


def menu_item(text):
    return Color.frame_button(ClickableIcon(_(text), 0))


class HelpMenu(WidgetWrap):

    def __init__(self, parent):
        self.parent = parent
        close = header_btn(_("Help"))
        about = menu_item(_("About the installer"))
        local = menu_item(_("Help on this screen"))
        keys = menu_item(_("Help on keyboard shortcuts"))
        entries = [
            about,
            local,
            hline,
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

        rows = [
            Columns([
                ('fixed', 1, tlcorner),
                hline,
                (widget_width(close), close),
                ('fixed', 1, trcorner),
                ]),
            ]
        for entry in entries:
            if isinstance(entry, Divider):
                left, right = ltee, rtee
            else:
                left = right = vline
            rows.append(Columns([
                ('fixed', 1, left),
                entry,
                ('fixed', 1, right),
                ]))
        rows.append(
            Columns([
                (1, blcorner),
                hline,
                (1, brcorner),
                ]))
        self.width = max([widget_width(b) for b in buttons]) + 2
        self.height = len(entries) + 2
        super().__init__(Color.frame_header(Filler(Pile(rows))))

    def keypress(self, size, key):
        if key == 'esc':
            self.parent.close_pop_up()
        else:
            return super().keypress(size, key)

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
